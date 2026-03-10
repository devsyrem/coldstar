"""
Tests for the ZK proof types module.

Tests dataclass creation, serialization (to_dict / from_dict),
mode parsing, and edge cases.
"""

import pytest
from src.zk.types import (
    BitProof,
    OwnershipProof,
    PolicyProof,
    ProofBundle,
    RangeProof,
    TransactionContext,
    TransactionMode,
    TransferEnvelope,
    VerificationCheck,
    VerificationResult,
    SigningSummary,
)


class TestTransactionMode:
    def test_from_str_strict_public(self):
        assert TransactionMode.from_str_strict("public") == TransactionMode.PUBLIC

    def test_from_str_strict_private(self):
        assert TransactionMode.from_str_strict("private") == TransactionMode.PRIVATE

    def test_from_str_strict_invalid(self):
        assert TransactionMode.from_str_strict("stealth") is None

    def test_from_str_strict_case(self):
        # from_str_strict lowercases input
        assert TransactionMode.from_str_strict("PUBLIC") == TransactionMode.PUBLIC
        assert TransactionMode.from_str_strict("Private") == TransactionMode.PRIVATE

    def test_requires_proofs(self):
        assert TransactionMode.PRIVATE.requires_proofs() is True
        assert TransactionMode.PUBLIC.requires_proofs() is False


class TestOwnershipProof:
    def test_roundtrip(self):
        p = OwnershipProof(
            public_key="aabbcc",
            commitment_r="112233",
            challenge="445566",
            response="778899",
            context_hash="aabb",
        )
        d = p.to_dict()
        p2 = OwnershipProof.from_dict(d)
        assert p2.public_key == "aabbcc"
        assert p2.challenge == "445566"
        assert p2.context_hash == "aabb"


class TestBitProof:
    def test_roundtrip(self):
        bp = BitProof(commitment="c1", e0="e0", s0="s0", e1="e1", s1="s1")
        d = bp.to_dict()
        bp2 = BitProof.from_dict(d)
        assert bp2.commitment == "c1"
        assert bp2.e0 == "e0"


class TestRangeProof:
    def test_roundtrip(self):
        bp = BitProof(commitment="c1", e0="e0", s0="s0", e1="e1", s1="s1")
        rp = RangeProof(
            value_commitment="vc",
            num_bits=8,
            bit_proofs=[bp],
            context_hash="ctx",
        )
        d = rp.to_dict()
        rp2 = RangeProof.from_dict(d)
        assert rp2.value_commitment == "vc"
        assert rp2.num_bits == 8
        assert len(rp2.bit_proofs) == 1
        assert rp2.bit_proofs[0].commitment == "c1"


class TestPolicyProof:
    def test_roundtrip(self):
        pp = PolicyProof(
            policy_id="transfer_limit",
            commitment="cm",
            response="rsp",
            challenge="ch",
            context_hash="ctx",
        )
        d = pp.to_dict()
        pp2 = PolicyProof.from_dict(d)
        assert pp2.policy_id == "transfer_limit"


class TestProofBundle:
    def test_roundtrip_full(self):
        op = OwnershipProof("pk", "cmr", "ch", "rsp", "ctx")
        rp = RangeProof("vc", 2, [], "ctx")
        pp = PolicyProof("policy1", "cm", "rsp", "ch", "ctx")
        bundle = ProofBundle(
            ownership_proof=op,
            range_proof=rp,
            policy_proofs=[pp],
            binding="bindval",
            nonce="n1",
            version="0.1.0",
        )
        d = bundle.to_dict()
        b2 = ProofBundle.from_dict(d)
        assert b2.binding == "bindval"
        assert b2.ownership_proof.public_key == "pk"
        assert b2.range_proof.value_commitment == "vc"
        assert b2.policy_proofs[0].policy_id == "policy1"

    def test_roundtrip_no_range(self):
        op = OwnershipProof("pk", "cmr", "ch", "rsp", "ctx")
        bundle = ProofBundle(
            ownership_proof=op,
            range_proof=None,
            policy_proofs=[],
            binding="b",
            nonce="n",
        )
        d = bundle.to_dict()
        b2 = ProofBundle.from_dict(d)
        assert b2.range_proof is None
        assert b2.policy_proofs == []


class TestTransactionContext:
    def test_roundtrip(self):
        ctx = TransactionContext(
            unsigned_tx_b64="dHgx",
            from_pubkey="sender123",
            to_pubkey="recip456",
            amount_lamports=1_000_000,
            fee_lamports=5000,
            recent_blockhash="hash123",
            mode=TransactionMode.PRIVATE,
            nonce="nonce1",
        )
        d = ctx.to_dict()
        ctx2 = TransactionContext.from_dict(d)
        assert ctx2.from_pubkey == "sender123"
        assert ctx2.to_pubkey == "recip456"
        assert ctx2.amount_lamports == 1_000_000
        assert ctx2.mode == TransactionMode.PRIVATE


class TestTransferEnvelope:
    def _make_ctx(self, mode=TransactionMode.PUBLIC):
        return TransactionContext(
            unsigned_tx_b64="dHgx",
            from_pubkey="sender",
            to_pubkey="recip",
            amount_lamports=500,
            fee_lamports=5000,
            recent_blockhash="hash",
            mode=mode,
            nonce="n1",
        )

    def test_roundtrip_public(self):
        ctx = self._make_ctx(TransactionMode.PUBLIC)
        env = TransferEnvelope(
            version="1.0.0",
            mode=TransactionMode.PUBLIC,
            created_at="2024-01-01T00:00:00Z",
            transaction=ctx,
            proof_bundle=None,
            integrity="hmac123",
        )
        d = env.to_dict()
        env2 = TransferEnvelope.from_dict(d)
        assert env2.mode == TransactionMode.PUBLIC
        assert env2.transaction.amount_lamports == 500
        assert env2.integrity == "hmac123"

    def test_json_roundtrip(self):
        ctx = self._make_ctx()
        env = TransferEnvelope(
            version="1.0.0",
            mode=TransactionMode.PUBLIC,
            created_at="2024-01-01T00:00:00Z",
            transaction=ctx,
            proof_bundle=None,
            integrity="",
        )
        json_str = env.to_json()
        env2 = TransferEnvelope.from_json(json_str)
        assert env2.transaction.from_pubkey == "sender"


class TestVerificationCheck:
    def test_to_dict(self):
        vc = VerificationCheck(name="test", passed=True, detail="ok")
        d = vc.to_dict()
        assert d["name"] == "test"
        assert d["passed"] is True


class TestVerificationResult:
    def test_structure(self):
        vr = VerificationResult(
            valid=True,
            checks=[VerificationCheck("c1", True, "ok")],
            summary="All passed",
        )
        d = vr.to_dict()
        assert d["valid"] is True
        assert len(d["checks"]) == 1


class TestSigningSummary:
    def test_display_public(self):
        ss = SigningSummary(
            destination="recipABC",
            amount_sol=1.0,
            fee_sol=0.000005,
            mode=TransactionMode.PUBLIC,
            proof_verified=False,
            proofs_verified_count=0,
        )
        text = ss.display()
        assert "PUBLIC" in text
        assert "recipABC" in text

    def test_display_private_approved(self):
        ss = SigningSummary(
            destination="recipXYZ",
            amount_sol=0.5,
            fee_sol=0.000005,
            mode=TransactionMode.PRIVATE,
            proof_verified=True,
            proofs_verified_count=3,
        )
        text = ss.display()
        assert "PRIVATE" in text
        assert "PASSED" in text
        assert "3" in text
