"""
Coldstar ZK — Zero-Knowledge Proof Module

Provides ZK proof generation, verification, and transaction privacy
for the Coldstar cold wallet system.
"""

from src.zk.engine import ZkProofEngine
from src.zk.types import (
    TransactionMode,
    OwnershipProof,
    RangeProof,
    PolicyProof,
    ProofBundle,
    TransferEnvelope,
    SigningSummary,
    VerificationResult,
)

__all__ = [
    "ZkProofEngine",
    "TransactionMode",
    "OwnershipProof",
    "RangeProof",
    "PolicyProof",
    "ProofBundle",
    "TransferEnvelope",
    "SigningSummary",
    "VerificationResult",
]
