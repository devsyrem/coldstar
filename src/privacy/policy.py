"""
Signing Policy Engine

Evaluates whether a transaction should be signed based on:
- Mode-specific policy constraints
- Proof validity (private mode)
- Transfer limits and destination allowlists
- Replay protection

Each mode has different requirements:
  PUBLIC:  Standard validation (amount, destination, format)
  PRIVATE: Full ZK proof chain + standard validation + proof binding
"""

import enum
import time
from dataclasses import dataclass, field
from typing import List, Optional, Set

from src.zk.types import (
    ProofBundle,
    TransactionMode,
    TransferEnvelope,
)


class PolicyCheckResult(enum.Enum):
    """Result of a single policy check."""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class PolicyCheck:
    """A single policy check with name, result, and details."""
    name: str
    result: PolicyCheckResult
    detail: str = ""


@dataclass
class PolicyEvaluation:
    """Complete result of policy evaluation for a transaction."""
    approved: bool
    mode: TransactionMode
    checks: List[PolicyCheck] = field(default_factory=list)
    reason: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def failed_checks(self) -> List[PolicyCheck]:
        return [c for c in self.checks if c.result == PolicyCheckResult.FAIL]

    def display(self) -> str:
        lines = [
            f"Policy Evaluation: {'APPROVED' if self.approved else 'REJECTED'}",
            f"Mode: {self.mode.value}",
        ]
        for check in self.checks:
            icon = "✓" if check.result == PolicyCheckResult.PASS else (
                "✗" if check.result == PolicyCheckResult.FAIL else "–"
            )
            lines.append(f"  {icon} {check.name}: {check.detail}")
        if self.reason:
            lines.append(f"Reason: {self.reason}")
        return "\n".join(lines)


class SigningPolicyEngine:
    """Evaluates signing policy for a transfer envelope.

    This is a lightweight policy layer on top of ZkProofEngine.validate_envelope().
    It wraps the TransferEnvelope type from types.py directly.
    """

    def __init__(
        self,
        max_transfer_lamports: int = 10_000_000_000,
        allowed_destinations: Optional[Set[str]] = None,
        require_destination_allowlist: bool = False,
    ):
        self.max_transfer_lamports = max_transfer_lamports
        self.allowed_destinations: Set[str] = allowed_destinations or set()
        self.require_destination_allowlist = require_destination_allowlist
        self._seen_nonces: Set[str] = set()

    def set_max_transfer(self, lamports: int):
        self.max_transfer_lamports = lamports

    def add_allowed_destination(self, address: str):
        self.allowed_destinations.add(address)

    def remove_allowed_destination(self, address: str):
        self.allowed_destinations.discard(address)

    def evaluate(self, envelope: TransferEnvelope) -> PolicyEvaluation:
        """Run all policy checks for a transfer envelope."""
        mode = envelope.mode
        checks: List[PolicyCheck] = []

        # 1. Mode validity
        checks.append(PolicyCheck(
            name="mode_valid",
            result=PolicyCheckResult.PASS,
            detail=f"Mode: {mode.value}",
        ))

        # 2. Envelope structure
        checks.append(self._check_structure(envelope))

        # 3. Amount within limits
        checks.append(self._check_amount(envelope))

        # 4. Destination check
        checks.append(self._check_destination(envelope))

        # 5. Replay protection
        checks.append(self._check_replay(envelope))

        # 6. Private-mode-only checks
        if mode == TransactionMode.PRIVATE:
            if envelope.proof_bundle is None:
                checks.append(PolicyCheck(
                    name="proof_bundle_present",
                    result=PolicyCheckResult.FAIL,
                    detail="Private mode requires a proof bundle",
                ))
            else:
                checks.append(PolicyCheck(
                    name="proof_bundle_present",
                    result=PolicyCheckResult.PASS,
                    detail="Proof bundle provided",
                ))
                checks.extend(self._check_proof_completeness(envelope.proof_bundle))
                checks.append(self._check_proof_binding(envelope))
        else:
            checks.append(PolicyCheck(
                name="proof_bundle_present",
                result=PolicyCheckResult.SKIP,
                detail="Not required for public mode",
            ))

        failed = [c for c in checks if c.result == PolicyCheckResult.FAIL]
        approved = len(failed) == 0
        reason = "; ".join(f"{c.name}: {c.detail}" for c in failed) if not approved else ""

        nonce = envelope.transaction.nonce
        if approved and nonce:
            self._seen_nonces.add(nonce)

        return PolicyEvaluation(approved=approved, mode=mode, checks=checks, reason=reason)

    # ── Individual Checks ──────────────────────────

    def _check_structure(self, envelope: TransferEnvelope) -> PolicyCheck:
        issues = []
        tx = envelope.transaction
        if not tx.from_pubkey:
            issues.append("missing sender")
        if not tx.to_pubkey:
            issues.append("missing recipient")
        if tx.amount_lamports < 0:
            issues.append("negative amount")
        if issues:
            return PolicyCheck(name="structure", result=PolicyCheckResult.FAIL,
                               detail=f"Invalid: {', '.join(issues)}")
        return PolicyCheck(name="structure", result=PolicyCheckResult.PASS,
                           detail="Envelope structure valid")

    def _check_amount(self, envelope: TransferEnvelope) -> PolicyCheck:
        amount = envelope.transaction.amount_lamports
        if amount > self.max_transfer_lamports:
            return PolicyCheck(name="amount_limit", result=PolicyCheckResult.FAIL,
                               detail=f"Amount {amount} exceeds limit {self.max_transfer_lamports}")
        return PolicyCheck(name="amount_limit", result=PolicyCheckResult.PASS,
                           detail=f"Amount {amount} within limit {self.max_transfer_lamports}")

    def _check_destination(self, envelope: TransferEnvelope) -> PolicyCheck:
        recipient = envelope.transaction.to_pubkey
        if not self.require_destination_allowlist:
            return PolicyCheck(name="destination", result=PolicyCheckResult.PASS,
                               detail="Destination allowlist not enforced")
        if not self.allowed_destinations:
            return PolicyCheck(name="destination", result=PolicyCheckResult.FAIL,
                               detail="Destination allowlist is enforced but empty")
        if recipient in self.allowed_destinations:
            return PolicyCheck(name="destination", result=PolicyCheckResult.PASS,
                               detail=f"Destination {recipient[:8]}… is allowed")
        return PolicyCheck(name="destination", result=PolicyCheckResult.FAIL,
                           detail=f"Destination {recipient[:8]}… not in allowlist")

    def _check_replay(self, envelope: TransferEnvelope) -> PolicyCheck:
        nonce = envelope.transaction.nonce
        if not nonce:
            return PolicyCheck(name="replay", result=PolicyCheckResult.FAIL,
                               detail="Missing nonce")
        if nonce in self._seen_nonces:
            return PolicyCheck(name="replay", result=PolicyCheckResult.FAIL,
                               detail=f"Nonce '{nonce[:16]}…' already used")
        return PolicyCheck(name="replay", result=PolicyCheckResult.PASS,
                           detail="Nonce is fresh")

    def _check_proof_completeness(self, bundle: ProofBundle) -> List[PolicyCheck]:
        checks = []
        if bundle.ownership_proof is not None:
            checks.append(PolicyCheck(name="ownership_proof", result=PolicyCheckResult.PASS,
                                      detail="Ownership proof present"))
        else:
            checks.append(PolicyCheck(name="ownership_proof", result=PolicyCheckResult.FAIL,
                                      detail="Missing ownership proof"))
        if bundle.range_proof is not None:
            checks.append(PolicyCheck(name="range_proof", result=PolicyCheckResult.PASS,
                                      detail="Range proof present"))
        else:
            checks.append(PolicyCheck(name="range_proof", result=PolicyCheckResult.SKIP,
                                      detail="Range proof not included"))
        if bundle.policy_proofs:
            checks.append(PolicyCheck(name="policy_proofs", result=PolicyCheckResult.PASS,
                                      detail=f"{len(bundle.policy_proofs)} policy proof(s)"))
        else:
            checks.append(PolicyCheck(name="policy_proofs", result=PolicyCheckResult.SKIP,
                                      detail="No policy proofs"))
        return checks

    def _check_proof_binding(self, envelope: TransferEnvelope) -> PolicyCheck:
        bundle = envelope.proof_bundle
        if bundle is None or not bundle.binding:
            return PolicyCheck(name="proof_binding", result=PolicyCheckResult.FAIL,
                               detail="No proof binding")
        return PolicyCheck(name="proof_binding", result=PolicyCheckResult.PASS,
                           detail="Proof binding present")
