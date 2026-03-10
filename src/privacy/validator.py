"""
Privacy Validator

Orchestrates the full validation pipeline for a transaction:
  1. Mode selection (explicit, locked)
  2. Proof generation (private mode)
  3. Envelope construction
  4. Policy evaluation
  5. Final sign/reject decision

This is the top-level API that the CLI should call.
"""

from dataclasses import dataclass
from typing import Optional

from src.zk.types import (
    ProofBundle,
    TransactionContext,
    TransactionMode,
    TransferEnvelope,
    VerificationResult,
    SigningSummary,
)
from src.zk.engine import ZkProofEngine
from src.privacy.mode import ModeSelector, ModeState
from src.privacy.policy import PolicyEvaluation, SigningPolicyEngine


@dataclass
class ValidationResult:
    """Final validation result — the single gate for signing."""
    approved: bool
    mode: TransactionMode
    envelope: Optional[TransferEnvelope] = None
    proof_bundle: Optional[ProofBundle] = None
    policy_evaluation: Optional[PolicyEvaluation] = None
    verification_result: Optional[VerificationResult] = None
    signing_summary: Optional[SigningSummary] = None
    reason: str = ""

    def display(self) -> str:
        lines = [
            "╔════════════════════════════════════════╗",
            f"║  Transaction Validation: {'APPROVED' if self.approved else 'REJECTED':^14s}  ║",
            f"║  Mode: {self.mode.value:^31s}  ║",
            "╚════════════════════════════════════════╝",
        ]
        if self.signing_summary:
            lines.append("")
            lines.append(self.signing_summary.display())
        if self.policy_evaluation:
            lines.append("")
            lines.append(self.policy_evaluation.display())
        if self.reason:
            lines.append("")
            lines.append(f"Reason: {self.reason}")
        return "\n".join(lines)


class PrivacyValidator:
    """Top-level validator that orchestrates the entire transaction
    validation pipeline using ZkProofEngine.

    Usage:
        validator = PrivacyValidator()
        validator.select_mode("private")

        result = validator.validate_transaction(
            tx_context=TransactionContext(...),
            secret_key_hex="...",  # only for private mode
        )

        if result.approved:
            # proceed to signing with result.envelope
            ...
    """

    def __init__(
        self,
        max_transfer_lamports: int = 10_000_000_000,
        allowed_destinations: Optional[set] = None,
        require_destination_allowlist: bool = False,
    ):
        self._engine = ZkProofEngine()
        self._mode_selector = ModeSelector()
        self._policy_engine = SigningPolicyEngine(
            max_transfer_lamports=max_transfer_lamports,
            allowed_destinations=allowed_destinations,
            require_destination_allowlist=require_destination_allowlist,
        )

    # ── Mode selection ────────────────────────────

    @property
    def mode(self) -> Optional[TransactionMode]:
        return self._mode_selector.mode

    @property
    def mode_state(self) -> ModeState:
        return self._mode_selector.state

    def select_mode(self, mode_str: str):
        """Select the transaction mode (public / private)."""
        self._mode_selector.select(mode_str)

    def reset(self):
        """Reset for a new transaction."""
        self._mode_selector.reset()

    # ── Configuration pass-through ────────────────

    def set_max_transfer(self, lamports: int):
        self._policy_engine.set_max_transfer(lamports)
        self._engine.set_max_transfer(lamports)

    def add_allowed_destination(self, address: str):
        self._policy_engine.add_allowed_destination(address)
        self._engine.add_allowed_destination(address)

    # ── Full validation pipeline ──────────────────

    def validate_transaction(
        self,
        tx_context: TransactionContext,
        secret_key_hex: Optional[str] = None,
    ) -> ValidationResult:
        """Run the complete validation pipeline.

        For public mode:
            - Build a public envelope
            - Run policy checks + engine validation

        For private mode:
            - Generate all ZK proofs
            - Compute binding
            - Build a private envelope with HMAC
            - Run full policy + engine validation

        Args:
            tx_context: The full transaction context
            secret_key_hex: Secret key hex string (required for private mode)

        Returns:
            ValidationResult with approval decision, envelope, and details
        """
        if self._mode_selector.mode is None:
            return ValidationResult(
                approved=False,
                mode=TransactionMode.PUBLIC,
                reason="No mode selected. Call select_mode() first.",
            )

        mode = self._mode_selector.mode

        # Ensure mode matches context
        if tx_context.mode != mode:
            return ValidationResult(
                approved=False,
                mode=mode,
                reason=f"Mode mismatch: selector={mode.value}, context={tx_context.mode.value}",
            )

        try:
            if mode == TransactionMode.PUBLIC:
                return self._validate_public(tx_context)
            else:
                if secret_key_hex is None:
                    return ValidationResult(
                        approved=False,
                        mode=TransactionMode.PRIVATE,
                        reason="Private mode requires secret_key_hex",
                    )
                return self._validate_private(tx_context, secret_key_hex)
        except Exception as e:
            return ValidationResult(
                approved=False,
                mode=mode,
                reason=f"Validation error: {e}",
            )

    def _validate_public(self, tx_context: TransactionContext) -> ValidationResult:
        """Public mode validation."""
        self._mode_selector.lock()

        envelope = self._engine.build_public_envelope(tx_context)

        # Run engine validation
        vr, summary = self._engine.validate_envelope(envelope)

        # Run policy evaluation
        evaluation = self._policy_engine.evaluate(envelope)

        approved = vr.valid and evaluation.approved
        reason = ""
        if not vr.valid:
            reason = vr.summary
        if not evaluation.approved:
            reason = (reason + "; " if reason else "") + evaluation.reason

        return ValidationResult(
            approved=approved,
            mode=TransactionMode.PUBLIC,
            envelope=envelope,
            verification_result=vr,
            signing_summary=summary,
            policy_evaluation=evaluation,
            reason=reason,
        )

    def _validate_private(
        self,
        tx_context: TransactionContext,
        secret_key_hex: str,
    ) -> ValidationResult:
        """Private mode validation — full ZK proof pipeline."""
        # Generate proof bundle
        proof_bundle = self._engine.generate_proof_bundle(
            tx_context=tx_context,
            secret_key_hex=secret_key_hex,
        )

        # Lock mode after proof generation
        self._mode_selector.lock()

        # Build private envelope
        envelope = self._engine.build_private_envelope(tx_context, proof_bundle)

        # Run engine validation
        vr, summary = self._engine.validate_envelope(envelope)

        # Run policy evaluation
        evaluation = self._policy_engine.evaluate(envelope)

        approved = vr.valid and evaluation.approved
        reason = ""
        if not vr.valid:
            reason = vr.summary
        if not evaluation.approved:
            reason = (reason + "; " if reason else "") + evaluation.reason

        return ValidationResult(
            approved=approved,
            mode=TransactionMode.PRIVATE,
            envelope=envelope,
            proof_bundle=proof_bundle,
            verification_result=vr,
            signing_summary=summary,
            policy_evaluation=evaluation,
            reason=reason,
        )

    # ── Verification (offline signer side) ────────

    def verify_envelope(self, envelope: TransferEnvelope) -> ValidationResult:
        """Verify a received envelope (called by offline signer).

        Args:
            envelope: The transfer envelope to verify

        Returns:
            ValidationResult
        """
        vr, summary = self._engine.validate_envelope(envelope)
        evaluation = self._policy_engine.evaluate(envelope)

        approved = vr.valid and evaluation.approved
        reason = ""
        if not vr.valid:
            reason = vr.summary
        if not evaluation.approved:
            reason = (reason + "; " if reason else "") + evaluation.reason

        return ValidationResult(
            approved=approved,
            mode=envelope.mode,
            envelope=envelope,
            proof_bundle=envelope.proof_bundle,
            verification_result=vr,
            signing_summary=summary,
            policy_evaluation=evaluation,
            reason=reason,
        )
