"""
ZK Proof Types for Coldstar.dev

These types mirror the Rust types in coldstar_zk/src/types.rs.
They provide Python-native representations for proof artifacts,
transaction contexts, and transfer envelopes.
"""

import json
import enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


class TransactionMode(enum.Enum):
    """Transaction mode — explicitly chosen by the user before signing.

    SECURITY: This must never have a default. The user must
    explicitly select a mode. Ambiguous states are rejected.
    """
    PUBLIC = "public"
    PRIVATE = "private"

    def requires_proofs(self) -> bool:
        return self == TransactionMode.PRIVATE

    @classmethod
    def from_str_strict(cls, s: str) -> Optional["TransactionMode"]:
        """Parse a mode string. Returns None for invalid strings."""
        s = s.strip().lower()
        if s == "public":
            return cls.PUBLIC
        elif s == "private":
            return cls.PRIVATE
        return None


@dataclass
class OwnershipProof:
    """Schnorr NIZK proof of wallet ownership."""
    public_key: str        # hex
    commitment_r: str      # hex
    challenge: str         # hex
    response: str          # hex
    context_hash: str      # hex

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OwnershipProof":
        return cls(**d)


@dataclass
class BitProof:
    """A single bit proof within a range proof."""
    commitment: str  # hex
    e0: str          # hex
    s0: str          # hex
    e1: str          # hex
    s1: str          # hex

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BitProof":
        return cls(**d)


@dataclass
class RangeProof:
    """Range proof that a committed value lies in [0, 2^n)."""
    value_commitment: str  # hex
    num_bits: int
    bit_proofs: List[BitProof]
    context_hash: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["bit_proofs"] = [bp.to_dict() if isinstance(bp, BitProof) else bp for bp in self.bit_proofs]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RangeProof":
        bit_proofs = [BitProof.from_dict(bp) if isinstance(bp, dict) else bp for bp in d.get("bit_proofs", [])]
        return cls(
            value_commitment=d["value_commitment"],
            num_bits=d["num_bits"],
            bit_proofs=bit_proofs,
            context_hash=d["context_hash"],
        )


@dataclass
class PolicyProof:
    """Policy compliance proof."""
    policy_id: str
    commitment: str   # hex
    response: str     # hex
    challenge: str    # hex
    context_hash: str # hex

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PolicyProof":
        return cls(**d)


@dataclass
class ProofBundle:
    """Bundle of all proofs for a private transaction."""
    ownership_proof: OwnershipProof
    range_proof: Optional[RangeProof]
    policy_proofs: List[PolicyProof]
    binding: str       # hex
    nonce: str         # hex
    version: str = "0.1.0"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "ownership_proof": self.ownership_proof.to_dict(),
            "range_proof": self.range_proof.to_dict() if self.range_proof else None,
            "policy_proofs": [pp.to_dict() for pp in self.policy_proofs],
            "binding": self.binding,
            "nonce": self.nonce,
            "version": self.version,
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProofBundle":
        ownership = OwnershipProof.from_dict(d["ownership_proof"])
        range_proof = RangeProof.from_dict(d["range_proof"]) if d.get("range_proof") else None
        policy_proofs = [PolicyProof.from_dict(pp) for pp in d.get("policy_proofs", [])]
        return cls(
            ownership_proof=ownership,
            range_proof=range_proof,
            policy_proofs=policy_proofs,
            binding=d["binding"],
            nonce=d["nonce"],
            version=d.get("version", "0.1.0"),
        )


@dataclass
class TransactionContext:
    """Transaction context — metadata about the transaction being signed."""
    unsigned_tx_b64: str
    from_pubkey: str
    to_pubkey: str
    amount_lamports: int
    fee_lamports: int
    recent_blockhash: str
    mode: TransactionMode
    nonce: str
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unsigned_tx_b64": self.unsigned_tx_b64,
            "from_pubkey": self.from_pubkey,
            "to_pubkey": self.to_pubkey,
            "amount_lamports": self.amount_lamports,
            "fee_lamports": self.fee_lamports,
            "recent_blockhash": self.recent_blockhash,
            "mode": self.mode.value,
            "nonce": self.nonce,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TransactionContext":
        mode = TransactionMode.from_str_strict(d["mode"])
        if mode is None:
            raise ValueError(f"Invalid transaction mode: {d['mode']}")
        return cls(
            unsigned_tx_b64=d["unsigned_tx_b64"],
            from_pubkey=d["from_pubkey"],
            to_pubkey=d["to_pubkey"],
            amount_lamports=d["amount_lamports"],
            fee_lamports=d["fee_lamports"],
            recent_blockhash=d["recent_blockhash"],
            mode=mode,
            nonce=d["nonce"],
            created_at=d.get("created_at", ""),
        )


@dataclass
class TransferEnvelope:
    """Transfer envelope — the sealed package between online and offline machines."""
    version: str
    mode: TransactionMode
    created_at: str
    transaction: TransactionContext
    proof_bundle: Optional[ProofBundle]
    integrity: str

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "version": self.version,
            "mode": self.mode.value,
            "created_at": self.created_at,
            "transaction": self.transaction.to_dict(),
            "proof_bundle": self.proof_bundle.to_dict() if self.proof_bundle else None,
            "integrity": self.integrity,
        }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TransferEnvelope":
        mode = TransactionMode.from_str_strict(d["mode"])
        if mode is None:
            raise ValueError(f"Invalid mode: {d['mode']}")
        tx = TransactionContext.from_dict(d["transaction"])
        proof_bundle = ProofBundle.from_dict(d["proof_bundle"]) if d.get("proof_bundle") else None
        return cls(
            version=d["version"],
            mode=mode,
            created_at=d["created_at"],
            transaction=tx,
            proof_bundle=proof_bundle,
            integrity=d.get("integrity", ""),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "TransferEnvelope":
        return cls.from_dict(json.loads(json_str))


@dataclass
class VerificationCheck:
    """A single verification check result."""
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    """Result of proof verification on the offline signer."""
    valid: bool
    checks: List[VerificationCheck]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
        }


@dataclass
class SigningSummary:
    """Human-readable transaction summary displayed before signing.

    SECURITY: This is the last thing the user sees before confirming.
    It MUST accurately reflect the transaction content.
    """
    destination: str
    amount_sol: float
    fee_sol: float
    mode: TransactionMode
    proof_verified: bool
    proofs_verified_count: int
    warnings: List[str] = field(default_factory=list)

    LAMPORTS_PER_SOL = 1_000_000_000

    def display(self) -> str:
        lines = [
            "╔══════════════════════════════════════════════════╗",
            "║           TRANSACTION SIGNING SUMMARY            ║",
            "╠══════════════════════════════════════════════════╣",
            f"║ Destination: {self.destination}",
            f"║ Amount:      {self.amount_sol:.9f} SOL",
            f"║ Fee:         {self.fee_sol:.9f} SOL",
            f"║ Mode:        {self.mode.value.upper()}",
        ]
        if self.mode.requires_proofs():
            status = "✓ PASSED" if self.proof_verified else "✗ FAILED"
            lines.append(f"║ Proofs:      {status} ({self.proofs_verified_count} verified)")
        for warning in self.warnings:
            lines.append(f"║ ⚠ WARNING:   {warning}")
        lines.append("╚══════════════════════════════════════════════════╝")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "destination": self.destination,
            "amount_sol": self.amount_sol,
            "fee_sol": self.fee_sol,
            "mode": self.mode.value,
            "proof_verified": self.proof_verified,
            "proofs_verified_count": self.proofs_verified_count,
            "warnings": self.warnings,
        }
