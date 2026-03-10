#!/usr/bin/env python3
"""
Coldstar ZK Transaction CLI

CLI commands for the zero-knowledge proof transaction layer.
Integrates with the existing CLI or can be used standalone.

Commands:
  coldstar tx create --mode public|private
  coldstar tx inspect --file <path>
  coldstar tx inspect-proof --file <path>
  coldstar tx export --output <path>
  coldstar tx import --input <path>
  coldstar tx guided
  coldstar zk init
  coldstar zk prove --sender ... --recipient ... --amount-lamports ...
  coldstar zk verify --envelope-file <path>
"""

import argparse
import json
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

from src.zk.types import (
    ProofBundle,
    TransactionContext,
    TransactionMode,
    TransferEnvelope,
    SigningSummary,
)
from src.zk.engine import ZkProofEngine
from src.privacy.mode import ModeSelector, ModeState
from src.privacy.policy import SigningPolicyEngine
from src.privacy.validator import PrivacyValidator, ValidationResult


# ── Rich display helpers ──────────────────────

def display_mode_selection(mode: TransactionMode):
    if mode == TransactionMode.PUBLIC:
        panel = Panel(
            "[bold white]PUBLIC TRANSACTION[/]\n\n"
            "• Standard Solana transfer\n"
            "• Transaction visible on-chain\n"
            "• No ZK proofs generated\n"
            "• Fastest path to signing",
            title="[green]Mode: PUBLIC[/]",
            border_style="green",
        )
    else:
        panel = Panel(
            "[bold white]PRIVATE TRANSACTION[/]\n\n"
            "• ZK proofs protect signing metadata\n"
            "• Ownership proof (Schnorr NIZK)\n"
            "• Range proof (amount in valid range)\n"
            "• Policy proof (compliant with limits)\n"
            "• Proof binding to transaction intent\n"
            "• HMAC integrity on envelope\n\n"
            "[dim]Note: On-chain data remains public (Solana limitation)[/]",
            title="[magenta]Mode: PRIVATE[/]",
            border_style="magenta",
        )
    console.print(panel)


def display_envelope(envelope: TransferEnvelope):
    tbl = Table(title="Transfer Envelope", show_header=True, header_style="bold cyan")
    tbl.add_column("Field", style="dim")
    tbl.add_column("Value")
    tx = envelope.transaction

    tbl.add_row("Mode", envelope.mode.value.upper())
    tbl.add_row("Version", envelope.version)
    tbl.add_row("Sender", tx.from_pubkey)
    tbl.add_row("Recipient", tx.to_pubkey)
    tbl.add_row("Amount (lamports)", f"{tx.amount_lamports:,}")
    tbl.add_row("Amount (SOL)", f"{tx.amount_lamports / 1_000_000_000:.9f}")
    tbl.add_row("Fee (lamports)", f"{tx.fee_lamports:,}")
    tbl.add_row("Blockhash", tx.recent_blockhash[:24] + "…" if len(tx.recent_blockhash) > 24 else tx.recent_blockhash)
    tbl.add_row("Nonce", tx.nonce[:32] + "…" if len(tx.nonce) > 32 else tx.nonce)
    tbl.add_row("Integrity", envelope.integrity[:32] + "…" if len(envelope.integrity) > 32 else envelope.integrity)
    tbl.add_row("Has Proofs", "Yes" if envelope.proof_bundle else "No")

    console.print(tbl)


def display_proof_bundle(bundle: ProofBundle):
    tbl = Table(title="ZK Proof Bundle", show_header=True, header_style="bold magenta")
    tbl.add_column("Proof", style="dim")
    tbl.add_column("Status")
    tbl.add_column("Details")

    if bundle.ownership_proof:
        op = bundle.ownership_proof
        tbl.add_row("Ownership (Schnorr)", "[green]✓ Present[/]",
                     f"pubkey: {op.public_key[:16]}…")
    else:
        tbl.add_row("Ownership", "[red]✗ Missing[/]", "")

    if bundle.range_proof:
        rp = bundle.range_proof
        tbl.add_row("Range", "[green]✓ Present[/]",
                     f"{rp.num_bits} bits, commitment: {rp.value_commitment[:16]}…")
    else:
        tbl.add_row("Range", "[dim]– Not included[/]", "")

    if bundle.policy_proofs:
        for pp in bundle.policy_proofs:
            tbl.add_row(f"Policy: {pp.policy_id}", "[green]✓ Present[/]", "")
    else:
        tbl.add_row("Policy proofs", "[dim]– None[/]", "")

    tbl.add_row("Binding", f"[green]✓[/] {bundle.binding[:32]}…" if bundle.binding else "[yellow]None[/]", "")

    console.print(tbl)


def display_validation_result(result: ValidationResult):
    if result.approved:
        style, status = "green", "APPROVED"
    else:
        style, status = "red", "REJECTED"

    panel_text = f"[bold white]{status}[/]\nMode: {result.mode.value.upper()}"
    if result.reason:
        panel_text += f"\n\n[dim]{result.reason}[/]"
    console.print(Panel(panel_text, title=f"[{style}]Validation Result[/]", border_style=style))

    if result.signing_summary:
        console.print(result.signing_summary.display())

    if result.verification_result:
        tbl = Table(title="Verification Checks", show_header=True, header_style="bold")
        tbl.add_column("Check")
        tbl.add_column("Result")
        tbl.add_column("Detail")
        for check in result.verification_result.checks:
            icon = "[green]✓ PASS[/]" if check.passed else "[red]✗ FAIL[/]"
            tbl.add_row(check.name, icon, check.detail)
        console.print(tbl)


# ── CLI class ─────────────────────────────────

class ColdstarZkCLI:
    """ZK transaction CLI."""

    def __init__(self):
        self.validator = PrivacyValidator()
        self.engine = ZkProofEngine()
        self._current_envelope: Optional[TransferEnvelope] = None
        self._current_bundle: Optional[ProofBundle] = None

    def tx_create(self, mode: str, from_pubkey: str, to_pubkey: str,
                  amount_lamports: int, fee_lamports: int, recent_blockhash: str,
                  unsigned_tx_b64: str, secret_key_hex: Optional[str] = None) -> ValidationResult:
        """Create a transaction with mode selection."""
        console.print()
        console.rule("[bold]Transaction Creation[/]")

        tx_mode = TransactionMode.from_str_strict(mode)
        if tx_mode is None:
            console.print("[red]Invalid mode. Use 'public' or 'private'.[/]")
            return ValidationResult(approved=False, mode=TransactionMode.PUBLIC,
                                    reason=f"Invalid mode: {mode}")

        display_mode_selection(tx_mode)

        nonce = self.engine.generate_nonce()
        ctx = TransactionContext(
            unsigned_tx_b64=unsigned_tx_b64,
            from_pubkey=from_pubkey,
            to_pubkey=to_pubkey,
            amount_lamports=amount_lamports,
            fee_lamports=fee_lamports,
            recent_blockhash=recent_blockhash,
            mode=tx_mode,
            nonce=nonce,
        )

        self.validator.reset()
        self.validator.select_mode(mode)

        result = self.validator.validate_transaction(ctx, secret_key_hex=secret_key_hex)

        display_validation_result(result)
        if result.envelope:
            display_envelope(result.envelope)
        if result.proof_bundle:
            display_proof_bundle(result.proof_bundle)

        self._current_envelope = result.envelope
        self._current_bundle = result.proof_bundle
        return result

    def tx_inspect(self, json_str: str):
        console.rule("[bold]Envelope Inspection[/]")
        try:
            envelope = TransferEnvelope.from_json(json_str)
            display_envelope(envelope)
            if envelope.proof_bundle:
                display_proof_bundle(envelope.proof_bundle)
        except Exception as e:
            console.print(f"[red]Failed to parse: {e}[/]")

    def zk_init(self):
        console.rule("[bold]ZK Subsystem Status[/]")
        engine = ZkProofEngine()
        rust = engine._rust_lib is not None
        tbl = Table(show_header=False, title="ZK Engine Status")
        tbl.add_column("Property", style="dim")
        tbl.add_column("Value")
        tbl.add_row("Rust ZK library",
                     "[green]Loaded[/]" if rust else "[yellow]Not found (Python fallback)[/]")
        tbl.add_row("Proof system", "Schnorr NIZK + Bit-decomposition Range + Hash Policy")
        tbl.add_row("Group", "Ristretto255 (curve25519-dalek)")
        tbl.add_row("Commitments", "Pedersen (v·G + r·H)")
        tbl.add_row("Transcript", "Fiat-Shamir (SHA-512, domain-separated)")
        tbl.add_row("Envelope integrity", "HMAC-SHA256")
        tbl.add_row("Range proof bits", "64")
        console.print(tbl)
        return rust

    def zk_prove(self, from_pubkey: str, to_pubkey: str, amount_lamports: int,
                 fee_lamports: int, recent_blockhash: str, unsigned_tx_b64: str,
                 secret_key_hex: str) -> Optional[ProofBundle]:
        console.rule("[bold]ZK Proof Generation[/]")
        nonce = self.engine.generate_nonce()
        ctx = TransactionContext(
            unsigned_tx_b64=unsigned_tx_b64,
            from_pubkey=from_pubkey,
            to_pubkey=to_pubkey,
            amount_lamports=amount_lamports,
            fee_lamports=fee_lamports,
            recent_blockhash=recent_blockhash,
            mode=TransactionMode.PRIVATE,
            nonce=nonce,
        )
        try:
            bundle = self.engine.generate_proof_bundle(ctx, secret_key_hex)
            console.print("[green]Proofs generated successfully.[/]")
            display_proof_bundle(bundle)
            self._current_bundle = bundle
            return bundle
        except Exception as e:
            console.print(f"[red]Proof generation failed: {e}[/]")
            return None

    def zk_verify(self, envelope_json: str) -> bool:
        console.rule("[bold]Envelope Verification[/]")
        try:
            envelope = TransferEnvelope.from_json(envelope_json)
            result = self.validator.verify_envelope(envelope)
            display_validation_result(result)
            return result.approved
        except Exception as e:
            console.print(f"[red]Verification failed: {e}[/]")
            return False

    def export_envelope(self, path: str) -> bool:
        if self._current_envelope is None:
            console.print("[red]No envelope to export.[/]")
            return False
        try:
            with open(path, "w") as f:
                f.write(self._current_envelope.to_json())
            console.print(f"[green]Exported to {path}[/]")
            return True
        except IOError as e:
            console.print(f"[red]Export failed: {e}[/]")
            return False

    def import_envelope(self, path: str) -> bool:
        try:
            with open(path) as f:
                self._current_envelope = TransferEnvelope.from_json(f.read())
            console.print(f"[green]Imported from {path}[/]")
            display_envelope(self._current_envelope)
            return True
        except Exception as e:
            console.print(f"[red]Import failed: {e}[/]")
            return False

    def guided_transaction(self):
        console.rule("[bold cyan]Guided Transaction Flow[/]")
        console.print()

        console.print("[bold]Step 1: Choose transaction mode[/]\n")
        console.print("  [green]1[/] Public  — Standard Solana transfer")
        console.print("  [magenta]2[/] Private — ZK-proof protected signing pipeline")
        console.print()

        choice = console.input("[bold]Select mode (1/2): [/]").strip()
        mode = "public" if choice == "1" else "private" if choice == "2" else None
        if mode is None:
            console.print("[red]Invalid choice.[/]")
            return None

        display_mode_selection(TransactionMode.from_str_strict(mode))

        console.print("[bold]Step 2: Transaction details[/]\n")
        from_pk = console.input("  Sender address: ").strip()
        to_pk = console.input("  Recipient address: ").strip()
        if not from_pk or not to_pk:
            console.print("[red]Both addresses required.[/]")
            return None

        try:
            sol = float(console.input("  Amount (SOL): ").strip())
            amount = int(sol * 1_000_000_000)
        except ValueError:
            console.print("[red]Invalid amount.[/]")
            return None

        secret_key_hex = None
        if mode == "private":
            console.print("\n[bold]Step 3: Secret key (for proof generation)[/]")
            console.print("[dim]Used locally for ZK proofs. Never transmitted.[/]")
            secret_key_hex = console.input("  Secret key (hex): ").strip()

        return self.tx_create(
            mode=mode,
            from_pubkey=from_pk,
            to_pubkey=to_pk,
            amount_lamports=amount,
            fee_lamports=5000,
            recent_blockhash="placeholder",
            unsigned_tx_b64="placeholder",
            secret_key_hex=secret_key_hex,
        )


# ── argparse ──────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coldstar", description="Coldstar ZK Transaction Layer")
    sub = parser.add_subparsers(dest="command")

    # tx
    tx = sub.add_parser("tx", help="Transaction commands")
    tx_sub = tx.add_subparsers(dest="tx_command")

    tx_create = tx_sub.add_parser("create", help="Create a transaction")
    tx_create.add_argument("--mode", required=True, choices=["public", "private"])
    tx_create.add_argument("--from-pubkey", required=True)
    tx_create.add_argument("--to-pubkey", required=True)
    tx_create.add_argument("--amount-lamports", type=int, required=True)
    tx_create.add_argument("--fee-lamports", type=int, default=5000)
    tx_create.add_argument("--recent-blockhash", default="placeholder")
    tx_create.add_argument("--unsigned-tx-b64", default="placeholder")
    tx_create.add_argument("--secret-key-hex", help="Required for private mode")

    tx_inspect = tx_sub.add_parser("inspect", help="Inspect an envelope")
    tx_inspect.add_argument("--file", required=True)

    tx_export = tx_sub.add_parser("export", help="Export envelope")
    tx_export.add_argument("--output", required=True)

    tx_import = tx_sub.add_parser("import", help="Import envelope")
    tx_import.add_argument("--input", required=True)

    tx_sub.add_parser("guided", help="Interactive guided flow")

    # zk
    zk = sub.add_parser("zk", help="ZK proof commands")
    zk_sub = zk.add_subparsers(dest="zk_command")

    zk_sub.add_parser("init", help="Check ZK subsystem status")

    zk_prove = zk_sub.add_parser("prove", help="Generate ZK proofs")
    zk_prove.add_argument("--from-pubkey", required=True)
    zk_prove.add_argument("--to-pubkey", required=True)
    zk_prove.add_argument("--amount-lamports", type=int, required=True)
    zk_prove.add_argument("--fee-lamports", type=int, default=5000)
    zk_prove.add_argument("--recent-blockhash", default="placeholder")
    zk_prove.add_argument("--unsigned-tx-b64", default="placeholder")
    zk_prove.add_argument("--secret-key-hex", required=True)
    zk_prove.add_argument("--output", help="Output file")

    zk_verify = zk_sub.add_parser("verify", help="Verify an envelope")
    zk_verify.add_argument("--envelope-file", required=True)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    cli = ColdstarZkCLI()

    if args.command == "tx":
        if args.tx_command == "create":
            cli.tx_create(
                mode=args.mode,
                from_pubkey=args.from_pubkey,
                to_pubkey=args.to_pubkey,
                amount_lamports=args.amount_lamports,
                fee_lamports=args.fee_lamports,
                recent_blockhash=args.recent_blockhash,
                unsigned_tx_b64=args.unsigned_tx_b64,
                secret_key_hex=args.secret_key_hex,
            )
        elif args.tx_command == "inspect":
            with open(args.file) as f:
                cli.tx_inspect(f.read())
        elif args.tx_command == "export":
            cli.export_envelope(args.output)
        elif args.tx_command == "import":
            cli.import_envelope(getattr(args, "input"))
        elif args.tx_command == "guided":
            cli.guided_transaction()
        else:
            parser.parse_args(["tx", "--help"])

    elif args.command == "zk":
        if args.zk_command == "init":
            cli.zk_init()
        elif args.zk_command == "prove":
            bundle = cli.zk_prove(
                from_pubkey=args.from_pubkey,
                to_pubkey=args.to_pubkey,
                amount_lamports=args.amount_lamports,
                fee_lamports=args.fee_lamports,
                recent_blockhash=args.recent_blockhash,
                unsigned_tx_b64=args.unsigned_tx_b64,
                secret_key_hex=args.secret_key_hex,
            )
            if bundle and args.output:
                with open(args.output, "w") as f:
                    json.dump(bundle.to_dict(), f, indent=2)
                console.print(f"[green]Proofs saved to {args.output}[/]")
        elif args.zk_command == "verify":
            with open(args.envelope_file) as f:
                cli.zk_verify(f.read())
        else:
            parser.parse_args(["zk", "--help"])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
