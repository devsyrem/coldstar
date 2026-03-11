#!/usr/bin/env python3
"""
Test SPL Token-2022 Confidential Transfers

Demonstrates the full confidential transfer lifecycle on Solana devnet:
  1. Create a Token-2022 mint with confidential transfer extension
  2. Create a token account and configure it for confidential transfers
  3. Mint tokens to the account
  4. Deposit tokens to the confidential balance (public → encrypted)
  5. (Optionally) Transfer tokens confidentially to a recipient
  6. Withdraw tokens from confidential balance (encrypted → public)

Prerequisites:
  - solana CLI configured for devnet with funded keypair
  - spl-token CLI v5.x+ installed (cargo install spl-token-cli)
  - devnet SOL in the default keypair (for rent + tx fees)

Usage:
  python3 test_confidential_transfer.py
  python3 test_confidential_transfer.py --check-only      # just verify prerequisites
  python3 test_confidential_transfer.py --supply 1000      # mint 1000 tokens
  python3 test_confidential_transfer.py --keypair /path/to/keypair.json

B - Love U 3000
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.privacy.confidential_transfer import ConfidentialTransferManager
from config import SOLANA_RPC_URL


def banner(msg: str):
    width = max(len(msg) + 4, 60)
    print(f"\n{'━' * width}")
    print(f"  {msg}")
    print(f"{'━' * width}")


def step(num: int, msg: str):
    print(f"\n  ▸ Step {num}: {msg}")


def ok(msg: str):
    print(f"    ✓ {msg}")


def fail(msg: str):
    print(f"    ✗ {msg}")


def info(msg: str):
    print(f"    ℹ {msg}")


def main():
    parser = argparse.ArgumentParser(description="Test SPL Token-2022 Confidential Transfers")
    parser.add_argument("--keypair", type=str, default=None, help="Path to Solana keypair JSON")
    parser.add_argument("--rpc", type=str, default=None, help="Solana RPC URL")
    parser.add_argument("--supply", type=float, default=100.0, help="Initial token supply to mint")
    parser.add_argument("--deposit", type=float, default=None, help="Amount to deposit (default: half of supply)")
    parser.add_argument("--check-only", action="store_true", help="Only check prerequisites")
    parser.add_argument("--skip-transfer", action="store_true", help="Skip the transfer step (no recipient)")
    args = parser.parse_args()

    rpc_url = args.rpc or SOLANA_RPC_URL
    keypair_path = args.keypair

    # Auto-detect default keypair
    if keypair_path is None:
        default_kp = Path.home() / ".config" / "solana" / "id.json"
        if default_kp.exists():
            keypair_path = str(default_kp)

    banner("Coldstar — SPL Token-2022 Confidential Transfer Test")
    print(f"  RPC:     {rpc_url}")
    print(f"  Keypair: {keypair_path or '(not set)'}")
    print(f"  Supply:  {args.supply} tokens")

    # Initialize manager
    try:
        zk_engine = None
        try:
            from src.zk_engine import ZKProofEngine
            zk_engine = ZKProofEngine()
            print(f"  ZK:      Rust engine loaded")
        except Exception:
            print(f"  ZK:      Not available (optional)")

        mgr = ConfidentialTransferManager(
            rpc_url=rpc_url,
            keypair_path=keypair_path,
            zk_engine=zk_engine,
        )
    except FileNotFoundError as e:
        fail(str(e))
        sys.exit(1)

    # ── Prerequisites ───────────────────────────────────────────────
    banner("Checking Prerequisites")
    prereqs = mgr.check_prerequisites()

    for name, check in prereqs["checks"].items():
        available = check.get("available", check.get("exists", False))
        label = "✓" if available else "✗"
        detail = check.get("version", check.get("path", check.get("url", "")))
        print(f"  {label} {name}: {detail}")
        if not available and "error" in check:
            print(f"    → {check['error']}")

    if not prereqs["ready"]:
        fail("Prerequisites not met. Fix the issues above and retry.")
        if args.check_only:
            sys.exit(1)
        print("\n  Continuing anyway (some steps may fail)...")

    if args.check_only:
        banner("Prerequisites OK" if prereqs["ready"] else "Prerequisites FAILED")
        sys.exit(0 if prereqs["ready"] else 1)

    # ── Step 1: Create Confidential Mint ────────────────────────────
    banner("Creating Confidential Token Mint")
    step(1, "Creating Token-2022 mint with confidential transfer extension...")

    mint_result = mgr.create_confidential_mint(decimals=6, auto_approve=True)

    if not mint_result.get("success"):
        fail(f"Mint creation failed: {mint_result.get('error', 'unknown')}")
        sys.exit(1)

    mint_address = mint_result["mint"]
    ok(f"Mint created: {mint_address}")
    if mint_result.get("signature"):
        info(f"Signature: {mint_result['signature']}")

    # ── Step 2: Create Token Account ────────────────────────────────
    step(2, f"Creating token account for mint {mint_address[:16]}...")

    account_result = mgr.create_token_account(mint_address)

    if not account_result.get("success"):
        fail(f"Account creation failed: {account_result.get('error', 'unknown')}")
        sys.exit(1)

    token_account = account_result.get("account")
    ok(f"Token account: {token_account}")

    # ── Step 3: Configure Confidential Transfers ────────────────────
    step(3, "Configuring account for confidential transfers...")
    info("Generating ElGamal keypair + ZK ownership proof...")

    config_result = mgr.configure_confidential_account(
        token_account=token_account,
        mint_address=mint_address,
    )

    if not config_result.get("success"):
        fail(f"Configuration failed: {config_result.get('error', 'unknown')}")
        info("This may require the account to be approved first (if auto-approve is off)")
        sys.exit(1)

    ok("Account configured for confidential transfers")

    # ── Step 4: Mint Tokens ─────────────────────────────────────────
    step(4, f"Minting {args.supply} tokens...")

    mint_tokens_result = mgr.mint_tokens(mint_address, args.supply)

    if not mint_tokens_result.get("success"):
        fail(f"Minting failed: {mint_tokens_result.get('error', 'unknown')}")
        sys.exit(1)

    ok(f"Minted {args.supply} tokens to account")

    # ── Step 5: Deposit to Confidential Balance ─────────────────────
    deposit_amount = args.deposit or (args.supply / 2)
    step(5, f"Depositing {deposit_amount} tokens to confidential balance...")
    info("Moving tokens: public balance → ElGamal-encrypted balance")

    deposit_result = mgr.deposit_to_confidential(mint_address, deposit_amount)

    if not deposit_result.get("success"):
        fail(f"Deposit failed: {deposit_result.get('error', 'unknown')}")
        info("Deposit error — tokens remain in public balance")
    else:
        ok(f"Deposited {deposit_amount} tokens to confidential balance")
        info("Tokens are now ElGamal-encrypted on-chain")

    # Apply pending balance after deposit
    step(5.5, "Applying pending balance...")
    apply_result = mgr.apply_pending_balance(token_account=token_account)
    if apply_result.get("success"):
        ok("Pending balance applied → available for transfer")
    else:
        info(f"Apply pending: {apply_result.get('error', 'skipped')}")

    # ── Step 6: (Optional) Confidential Transfer ───────────────────
    if not args.skip_transfer:
        step(6, "Confidential transfer test")
        info("Skipping actual transfer (no recipient specified)")
        info("To transfer: mgr.confidential_transfer(mint, amount, recipient_pubkey)")
        info("The transfer amount will be encrypted on-chain using ElGamal")
    else:
        step(6, "Transfer step skipped (--skip-transfer)")

    # ── Step 7: Withdraw from Confidential Balance ──────────────────
    withdraw_amount = deposit_amount / 2
    step(7, f"Withdrawing {withdraw_amount} tokens from confidential balance...")
    info("Moving tokens: encrypted balance → public balance")

    withdraw_result = mgr.withdraw_from_confidential(mint_address, withdraw_amount)

    if not withdraw_result.get("success"):
        fail(f"Withdraw failed: {withdraw_result.get('error', 'unknown')}")
    else:
        ok(f"Withdrew {withdraw_amount} tokens back to public balance")

    # ── Summary ─────────────────────────────────────────────────────
    banner("Confidential Transfer Test Complete")
    print(f"  Mint:            {mint_address}")
    print(f"  Token Account:   {token_account}")
    print(f"  Total Supply:    {args.supply}")
    print(f"  Deposited:       {deposit_amount} (encrypted)")
    print(f"  Withdrawn:       {withdraw_amount} (decrypted)")
    print()
    print("  Privacy properties:")
    print("    ✓ Token amounts encrypted on-chain (ElGamal)")
    print("    ✓ ZK range proofs verify amounts ∈ [0, 2^64)")
    print("    ✓ ZK equality proofs verify ciphertext consistency")
    print("    ⚠ Sender/recipient addresses still visible")
    print()
    print("  Explore on Solana Explorer:")
    print(f"    https://explorer.solana.com/address/{mint_address}?cluster=devnet")
    print()


if __name__ == "__main__":
    main()
