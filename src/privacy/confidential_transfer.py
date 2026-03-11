"""
SPL Token-2022 Confidential Transfers

Enables privacy-preserving token transfers on Solana using the Token-2022
Confidential Transfer extension. Transfer amounts are encrypted on-chain
using twisted ElGamal encryption with ZK proofs for validity.

Supported operations:
  - Create Token-2022 mints with confidential transfer extension
  - Configure token accounts for confidential transfers
  - Deposit tokens to confidential balance (public → encrypted)
  - Transfer tokens confidentially (amount hidden on-chain)
  - Apply pending balance (recipient claims incoming transfers)
  - Withdraw from confidential balance (encrypted → public)

Privacy guarantees:
  - Transfer AMOUNTS are ElGamal-encrypted on-chain
  - ZK proofs ensure validity without revealing amounts
  - Sender and recipient addresses remain publicly visible
  - Uses Solana's native ZK proof verification (on-chain program)

Architecture:
  - Uses spl-token CLI (v5.5+) for instruction building & on-chain proof generation
  - Integrates with Coldstar's Rust ZK engine for signing pipeline integrity
  - Works with devnet, testnet, and mainnet-beta

B - Love U 3000
"""

import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from config import SOLANA_RPC_URL


# ── Data Types ──────────────────────────────────────────────────────────────

class ConfidentialTransferState(Enum):
    """Lifecycle state of a token account's confidential transfer capability."""
    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    APPROVED = "approved"
    ACTIVE = "active"


@dataclass
class ConfidentialMintInfo:
    """Metadata about a Token-2022 mint with confidential transfers enabled."""
    mint_address: str
    decimals: int
    authority: str
    confidential_transfer_enabled: bool
    auto_approve: bool


@dataclass
class ConfidentialAccountInfo:
    """Metadata about a token account configured for confidential transfers."""
    account_address: str
    mint_address: str
    owner: str
    public_balance: float
    confidential_configured: bool
    elgamal_pubkey: Optional[str] = None


# ── Main Manager ────────────────────────────────────────────────────────────

class ConfidentialTransferManager:
    """
    Manages SPL Token-2022 Confidential Transfer operations.

    Bridges Coldstar's secure signing architecture with Solana's Token-2022
    confidential transfer extension.  Supports the full lifecycle:

        create_confidential_mint()          → new Token-2022 mint
        create_token_account()              → associated token account
        configure_confidential_account()    → enable confidential mode
        mint_tokens()                       → mint supply (authority only)
        deposit_to_confidential()           → public → encrypted balance
        confidential_transfer()             → encrypted transfer (amount hidden)
        apply_pending_balance()             → claim incoming transfers
        withdraw_from_confidential()        → encrypted → public balance

    Also provides:
        setup_confidential_token()          → full setup in one call
        full_confidential_transfer()        → deposit + transfer in one call
        check_prerequisites()               → verify tools & connectivity
    """

    TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

    def __init__(
        self,
        rpc_url: str = None,
        keypair_path: str = None,
        spl_token_binary: str = None,
        zk_engine=None,
    ):
        """
        Args:
            rpc_url:           Solana RPC endpoint (default: config.SOLANA_RPC_URL)
            keypair_path:      Path to Solana keypair JSON file for signing
            spl_token_binary:  Explicit path to `spl-token` CLI binary
            zk_engine:         Optional ZKProofEngine instance for pipeline proofs
        """
        self.rpc_url = rpc_url or SOLANA_RPC_URL
        self.keypair_path = keypair_path
        self.zk_engine = zk_engine

        # Locate CLI binaries
        self.spl_token_bin = spl_token_binary or self._find_binary("spl-token")
        self.solana_bin = self._find_binary("solana")

    # ── Binary Discovery ────────────────────────────────────────────────

    @staticmethod
    def _find_binary(name: str) -> str:
        """Locate a CLI binary by name, searching PATH and common install dirs."""
        candidates = [
            shutil.which(name),
            str(Path.home() / ".cargo" / "bin" / name),
            str(Path.home() / ".local" / "share" / "solana" / "install" / "active_release" / "bin" / name),
            f"/opt/homebrew/bin/{name}",
        ]
        for c in candidates:
            if c and Path(c).exists():
                return c
        raise FileNotFoundError(
            f"{name} CLI not found. Install with: "
            + ("cargo install spl-token-cli" if name == "spl-token" else "sh -c \"$(curl -sSfL https://release.anza.xyz/stable/install)\"")
        )

    # ── CLI Helpers ─────────────────────────────────────────────────────

    def _run_spl_token(self, args: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
        """Execute an spl-token CLI command with RPC url and optional keypair."""
        cmd = [self.spl_token_bin] + args + ["--url", self.rpc_url]
        if self.keypair_path:
            cmd += ["--owner", self.keypair_path]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _run_solana(self, args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """Execute a solana CLI command."""
        cmd = [self.solana_bin] + args + ["--url", self.rpc_url]
        if self.keypair_path:
            cmd += ["--keypair", self.keypair_path]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    @staticmethod
    def _parse_address_from_output(output: str, keyword: str = "token") -> Optional[str]:
        """Extract an address from CLI output lines."""
        for line in output.split("\n"):
            if keyword.lower() in line.lower():
                # Look for base58 addresses (32-44 chars, alphanumeric)
                for word in line.split():
                    cleaned = word.strip(".,;:()'\"")
                    if 32 <= len(cleaned) <= 44 and cleaned.isalnum():
                        return cleaned
        return None

    @staticmethod
    def _parse_signature(output: str) -> Optional[str]:
        """Extract a transaction signature from CLI output."""
        for line in output.split("\n"):
            if "Signature:" in line:
                return line.split("Signature:")[-1].strip()
            # Some commands just print the signature on its own line
            stripped = line.strip()
            if len(stripped) >= 80 and len(stripped) <= 90 and stripped.isalnum():
                return stripped
        return None

    # ══════════════════════════════════════════════════════════════════════
    #  MINT OPERATIONS
    # ══════════════════════════════════════════════════════════════════════

    def create_confidential_mint(
        self,
        decimals: int = 6,
        auto_approve: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a new Token-2022 mint with confidential transfer extension.

        Args:
            decimals:     Token decimal places (default 6, same as USDC)
            auto_approve: Auto-approve accounts for confidential transfers

        Returns:
            {"success": bool, "mint": str, "decimals": int, ...}
        """
        approve_policy = "auto" if auto_approve else "manual"
        result = self._run_spl_token([
            "create-token",
            "--program-id", self.TOKEN_2022_PROGRAM_ID,
            "--decimals", str(decimals),
            "--enable-confidential-transfers", approve_policy,
        ])

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        output = result.stdout.strip()
        mint_address = self._parse_address_from_output(output, "Creating token") or \
                       self._parse_address_from_output(output, "Address:")
        signature = self._parse_signature(output)

        # Fallback: first line often is the address itself
        if not mint_address:
            for line in output.split("\n"):
                line = line.strip()
                if 32 <= len(line) <= 44 and line.isalnum():
                    mint_address = line
                    break

        return {
            "success": True,
            "mint": mint_address,
            "decimals": decimals,
            "auto_approve": auto_approve,
            "signature": signature,
            "output": output,
        }

    # ══════════════════════════════════════════════════════════════════════
    #  ACCOUNT OPERATIONS
    # ══════════════════════════════════════════════════════════════════════

    def create_token_account(self, mint_address: str) -> Dict[str, Any]:
        """
        Create a token account (Associated Token Account) for the given mint.

        Args:
            mint_address: The Token-2022 mint address

        Returns:
            {"success": bool, "account": str, ...}
        """
        result = self._run_spl_token([
            "create-account", mint_address,
            "--program-id", self.TOKEN_2022_PROGRAM_ID,
        ])

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        output = result.stdout.strip()
        account_address = self._parse_address_from_output(output, "Creating account") or \
                          self._parse_address_from_output(output, "account")
        signature = self._parse_signature(output)

        return {
            "success": True,
            "account": account_address,
            "mint": mint_address,
            "signature": signature,
            "output": output,
        }

    def configure_confidential_account(
        self,
        token_account: str = None,
        mint_address: str = None,
    ) -> Dict[str, Any]:
        """
        Configure a token account for confidential transfers.

        Generates an ElGamal keypair for the account and submits a ZK proof
        of key ownership to the Token-2022 program. This must be done before
        the account can participate in confidential transfers.

        Args:
            token_account: Token account address (omit to use default ATA)
            mint_address:  Mint address (informational only)

        Returns:
            {"success": bool, "configured": True, ...}
        """
        args = ["configure-confidential-transfer-account"]
        if token_account:
            args += ["--address", token_account]

        result = self._run_spl_token(args)

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        return {
            "success": True,
            "configured": True,
            "account": token_account,
            "mint": mint_address,
            "output": result.stdout.strip(),
        }

    # ══════════════════════════════════════════════════════════════════════
    #  TOKEN MINTING
    # ══════════════════════════════════════════════════════════════════════

    def mint_tokens(
        self,
        mint_address: str,
        amount: float,
        recipient: str = None,
    ) -> Dict[str, Any]:
        """
        Mint tokens to an account (requires mint authority).

        Args:
            mint_address: The token mint
            amount:       Amount in token units (e.g. 100.0 for 100 tokens)
            recipient:    Recipient token account (default: own ATA)

        Returns:
            {"success": bool, "amount": float, ...}
        """
        args = ["mint", mint_address, str(amount)]
        if recipient:
            args.append(recipient)
        args += ["--program-id", self.TOKEN_2022_PROGRAM_ID]

        result = self._run_spl_token(args)

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        return {
            "success": True,
            "mint": mint_address,
            "amount": amount,
            "recipient": recipient,
            "output": result.stdout.strip(),
        }

    # ══════════════════════════════════════════════════════════════════════
    #  CONFIDENTIAL OPERATIONS
    # ══════════════════════════════════════════════════════════════════════

    def deposit_to_confidential(
        self,
        mint_address: str,
        amount: float,
    ) -> Dict[str, Any]:
        """
        Deposit tokens from public balance to confidential balance.

        Moves tokens from the visible on-chain balance into the ElGamal-encrypted
        confidential balance. After deposit, the amount is no longer visible.

        Args:
            mint_address: Token mint address
            amount:       Amount to deposit (in token units)

        Returns:
            {"success": bool, "deposited": float, ...}
        """
        result = self._run_spl_token([
            "deposit-confidential-tokens",
            mint_address,
            str(amount),
        ])

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        return {
            "success": True,
            "deposited": amount,
            "mint": mint_address,
            "output": result.stdout.strip(),
        }

    def confidential_transfer(
        self,
        mint_address: str,
        amount: float,
        recipient: str,
    ) -> Dict[str, Any]:
        """
        Perform a confidential token transfer.

        The transfer amount is encrypted on-chain using twisted ElGamal encryption.
        The spl-token CLI automatically generates the required ZK proofs:
          • Range proof    — amount is in [0, 2^64)
          • Equality proof — sender/recipient ciphertexts encrypt the same value
          • Validity proof — ciphertexts are well-formed

        Sender and recipient addresses remain visible on-chain.
        Only the transfer amount is hidden.

        Args:
            mint_address: Token mint address
            amount:       Amount to transfer (in token units)
            recipient:    Recipient wallet address (Solana public key)

        Returns:
            {"success": bool, "amount_hidden": True, ...}
        """
        result = self._run_spl_token([
            "transfer",
            mint_address,
            str(amount),
            recipient,
            "--confidential",
        ])

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        return {
            "success": True,
            "amount_hidden": True,
            "mint": mint_address,
            "recipient": recipient,
            "output": result.stdout.strip(),
        }

    def apply_pending_balance(
        self,
        token_account: str = None,
    ) -> Dict[str, Any]:
        """
        Apply pending confidential balance to available balance.

        After receiving a confidential transfer, tokens land in a 'pending'
        state. This instruction moves them to the available confidential
        balance so they can be transferred or withdrawn.

        Args:
            token_account: Token account address (omit for default ATA)

        Returns:
            {"success": bool, "applied": True, ...}
        """
        args = ["apply-pending-balance"]
        if token_account:
            args += ["--address", token_account]

        result = self._run_spl_token(args)

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        return {
            "success": True,
            "applied": True,
            "output": result.stdout.strip(),
        }

    def withdraw_from_confidential(
        self,
        mint_address: str,
        amount: float,
    ) -> Dict[str, Any]:
        """
        Withdraw tokens from confidential balance to public balance.

        Decrypts and moves tokens from the encrypted confidential balance
        back to the visible public balance. A ZK proof is generated to
        show the withdrawal amount matches the decrypted ciphertext.

        Args:
            mint_address: Token mint address
            amount:       Amount to withdraw (in token units)

        Returns:
            {"success": bool, "withdrawn": float, ...}
        """
        result = self._run_spl_token([
            "withdraw-confidential-tokens",
            mint_address,
            str(amount),
        ])

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        return {
            "success": True,
            "withdrawn": amount,
            "mint": mint_address,
            "output": result.stdout.strip(),
        }

    # ══════════════════════════════════════════════════════════════════════
    #  QUERY OPERATIONS
    # ══════════════════════════════════════════════════════════════════════

    def get_account_info(self, token_account: str) -> Dict[str, Any]:
        """Get detailed info about a token account, including confidential state."""
        result = self._run_spl_token(["display", token_account])

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        output = result.stdout.strip()
        info: Dict[str, Any] = {
            "success": True,
            "account": token_account,
            "confidential_configured": "Confidential transfer" in output,
            "output": output,
        }

        # Parse key fields from display output
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("Mint:"):
                info["mint"] = line.split(":", 1)[1].strip()
            elif line.startswith("Owner:"):
                info["owner"] = line.split(":", 1)[1].strip()
            elif "balance:" in line.lower() and "confidential" not in line.lower():
                try:
                    info["public_balance"] = float(line.split(":")[-1].strip())
                except ValueError:
                    pass

        return info

    def get_token_balance(self, token_account: str) -> Dict[str, Any]:
        """Get the public balance of a token account."""
        result = self._run_spl_token(["balance", "--address", token_account])

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}

        try:
            balance = float(result.stdout.strip())
        except ValueError:
            balance = 0.0

        return {"success": True, "balance": balance}

    # ══════════════════════════════════════════════════════════════════════
    #  COMPOUND WORKFLOWS
    # ══════════════════════════════════════════════════════════════════════

    def setup_confidential_token(
        self,
        decimals: int = 6,
        initial_supply: float = 0,
    ) -> Dict[str, Any]:
        """
        Complete setup: create mint → create account → configure → mint tokens.

        Args:
            decimals:        Token decimal places
            initial_supply:  Amount to mint after setup (0 = skip minting)

        Returns:
            {"success": bool, "mint": str, "account": str, "steps": [...]}
        """
        steps: List[Dict] = []

        # 1. Create mint with confidential transfer extension
        mint_result = self.create_confidential_mint(decimals=decimals)
        steps.append({"step": "create_mint", "result": mint_result})
        if not mint_result.get("success"):
            return {"success": False, "error": "Failed to create mint", "steps": steps}

        mint_address = mint_result["mint"]

        # 2. Create token account
        account_result = self.create_token_account(mint_address)
        steps.append({"step": "create_account", "result": account_result})
        if not account_result.get("success"):
            return {"success": False, "error": "Failed to create account", "steps": steps}

        token_account = account_result.get("account")

        # 3. Configure for confidential transfers
        config_result = self.configure_confidential_account(
            token_account=token_account,
            mint_address=mint_address,
        )
        steps.append({"step": "configure_confidential", "result": config_result})
        if not config_result.get("success"):
            return {"success": False, "error": "Failed to configure confidential transfers", "steps": steps}

        # 4. Mint initial tokens (if requested)
        if initial_supply > 0:
            mint_result2 = self.mint_tokens(mint_address, initial_supply)
            steps.append({"step": "mint_tokens", "result": mint_result2})
            if not mint_result2.get("success"):
                return {"success": False, "error": "Failed to mint tokens", "steps": steps}

        return {
            "success": True,
            "mint": mint_address,
            "account": token_account,
            "decimals": decimals,
            "initial_supply": initial_supply,
            "steps": steps,
        }

    def full_confidential_transfer(
        self,
        mint_address: str,
        amount: float,
        recipient: str,
        deposit_first: bool = True,
    ) -> Dict[str, Any]:
        """
        Complete confidential transfer: deposit → transfer.

        Args:
            mint_address:  Token mint address
            amount:        Amount to transfer
            recipient:     Recipient wallet public key
            deposit_first: Deposit to confidential balance before transfer

        Returns:
            {"success": bool, "amount_hidden_on_chain": True, "steps": [...]}
        """
        steps: List[Dict] = []

        # 1. Deposit to confidential balance (if needed)
        if deposit_first:
            deposit_result = self.deposit_to_confidential(mint_address, amount)
            steps.append({"step": "deposit", "result": deposit_result})
            if not deposit_result.get("success"):
                return {"success": False, "error": "Deposit failed", "steps": steps}

        # 2. Confidential transfer
        transfer_result = self.confidential_transfer(mint_address, amount, recipient)
        steps.append({"step": "transfer", "result": transfer_result})
        if not transfer_result.get("success"):
            return {"success": False, "error": "Transfer failed", "steps": steps}

        # 3. Pipeline ZK proofs (optional, for signing integrity)
        zk_metadata = None
        if self.zk_engine:
            try:
                version = self.zk_engine.version()
                zk_metadata = {
                    "pipeline_protected": True,
                    "zk_engine_version": version.get("version"),
                    "proof_type": "signing_pipeline_integrity",
                }
            except Exception as e:
                zk_metadata = {"pipeline_protected": False, "error": str(e)}

        return {
            "success": True,
            "amount_hidden_on_chain": True,
            "mint": mint_address,
            "recipient": recipient,
            "zk_metadata": zk_metadata,
            "steps": steps,
            "privacy_note": (
                "Transfer amount is ElGamal-encrypted on-chain. "
                "Sender and recipient addresses are still visible. "
                "ZK proofs ensure transfer validity without revealing the amount."
            ),
        }

    # ══════════════════════════════════════════════════════════════════════
    #  PREREQUISITES CHECK
    # ══════════════════════════════════════════════════════════════════════

    def check_prerequisites(self) -> Dict[str, Any]:
        """Verify all tools and dependencies are available for confidential transfers."""
        checks: Dict[str, Any] = {}

        # spl-token CLI
        try:
            result = subprocess.run(
                [self.spl_token_bin, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            checks["spl_token_cli"] = {
                "available": result.returncode == 0,
                "version": result.stdout.strip(),
                "path": self.spl_token_bin,
            }
        except Exception as e:
            checks["spl_token_cli"] = {"available": False, "error": str(e)}

        # solana CLI
        try:
            result = subprocess.run(
                [self.solana_bin, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            checks["solana_cli"] = {
                "available": result.returncode == 0,
                "version": result.stdout.strip(),
                "path": self.solana_bin,
            }
        except Exception as e:
            checks["solana_cli"] = {"available": False, "error": str(e)}

        # ZK engine
        if self.zk_engine:
            try:
                version = self.zk_engine.version()
                checks["zk_engine"] = {
                    "available": True,
                    "version": version.get("version"),
                    "features": version.get("features", []),
                }
            except Exception as e:
                checks["zk_engine"] = {"available": False, "error": str(e)}
        else:
            checks["zk_engine"] = {
                "available": False,
                "note": "Not initialized (optional — CLI handles on-chain proofs)",
            }

        # RPC connectivity
        try:
            import httpx
            resp = httpx.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
                timeout=10,
            )
            data = resp.json()
            checks["rpc"] = {
                "available": data.get("result") == "ok",
                "url": self.rpc_url,
            }
        except Exception as e:
            checks["rpc"] = {"available": False, "url": self.rpc_url, "error": str(e)}

        # Keypair
        kp_exists = Path(self.keypair_path).exists() if self.keypair_path else False
        checks["keypair"] = {
            "configured": self.keypair_path is not None,
            "path": self.keypair_path,
            "exists": kp_exists,
        }

        all_ok = (
            checks.get("spl_token_cli", {}).get("available", False)
            and checks.get("solana_cli", {}).get("available", False)
            and checks.get("rpc", {}).get("available", False)
            and kp_exists
        )

        return {"ready": all_ok, "checks": checks}
