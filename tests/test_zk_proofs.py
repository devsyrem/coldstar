"""
Tests for the ZK proof engine.

Tests proof generation/verification (Python fallback path),
envelope construction, HMAC integrity, and the full pipeline.
"""

import json
import pytest

from src.zk.engine import ZkProofEngine
from src.zk.types import (
    ProofBundle,
    TransactionContext,
    TransactionMode,
    TransferEnvelope,
)


@pytest.fixture
def engine():
    return ZkProofEngine()


@pytest.fixture
def secret_key_hex():
    """A deterministic 32-byte key hex for testing."""
    return "00" * 32


def _make_ctx(mode=TransactionMode.PRIVATE, nonce="testnonce1",
              amount=500_000_000, from_pk="SenderPK", to_pk="RecipPK"):
    return TransactionContext(
        unsigned_tx_b64="dHgx",
        from_pubkey=from_pk,
        to_pubkey=to_pk,
        amount_lamports=amount,
        fee_lamports=5000,
        recent_blockhash="blockhash123",
        mode=mode,
        nonce=nonce,
    )


# ── Nonce generation ──────────────────────────

class TestNonce:
    def test_nonce_is_hex(self, engine):
        nonce = engine.generate_nonce()
        bytes.fromhex(nonce)  # should not raise

    def test_nonce_is_unique(self, engine):
        nonces = {engine.generate_nonce() for _ in range(100)}
        assert len(nonces) == 100


# ── Public envelope ───────────────────────────

class TestPublicEnvelope:
    def test_build_public_envelope(self, engine):
        ctx = _make_ctx(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx)
        assert env.mode == TransactionMode.PUBLIC
        assert env.transaction.from_pubkey == "SenderPK"
        assert env.proof_bundle is None
        assert env.integrity  # HMAC should be set

    def test_public_envelope_no_proofs(self, engine):
        ctx = _make_ctx(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx)
        assert env.proof_bundle is None


# ── Private envelope ──────────────────────────

class TestPrivateEnvelope:
    def test_build_private_envelope(self, engine, secret_key_hex):
        ctx = _make_ctx(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        env = engine.build_private_envelope(ctx, bundle)
        assert env.mode == TransactionMode.PRIVATE
        assert env.proof_bundle is not None
        assert env.integrity  # HMAC

    def test_private_envelope_integrity(self, engine, secret_key_hex):
        ctx = _make_ctx(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        env = engine.build_private_envelope(ctx, bundle)
        assert engine.verify_envelope_integrity(env) is True

    def test_tampered_envelope_fails_integrity(self, engine, secret_key_hex):
        ctx = _make_ctx(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        env = engine.build_private_envelope(ctx, bundle)
        # Tamper
        env.transaction.amount_lamports = 999_999_999
        assert engine.verify_envelope_integrity(env) is False


# ── Proof generation ──────────────────────────

class TestProofGeneration:
    def test_generate_proof_bundle(self, engine, secret_key_hex):
        ctx = _make_ctx(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        assert bundle.ownership_proof is not None
        assert bundle.range_proof is not None
        assert bundle.binding  # non-empty

    def test_proof_bundle_serialization(self, engine, secret_key_hex):
        ctx = _make_ctx(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        d = bundle.to_dict()
        json_str = json.dumps(d)
        d2 = json.loads(json_str)
        bundle2 = ProofBundle.from_dict(d2)
        assert bundle2.binding == bundle.binding
        assert bundle2.ownership_proof.public_key == bundle.ownership_proof.public_key


# ── Ownership proof ───────────────────────────

class TestOwnershipProof:
    def test_prove_and_verify(self, engine, secret_key_hex):
        ctx_hash = b"context_data"
        proof = engine.prove_ownership(secret_key_hex, ctx_hash)
        assert proof is not None
        assert proof.public_key

    def test_verify_ownership(self, engine, secret_key_hex):
        ctx_hash = b"context_data"
        proof = engine.prove_ownership(secret_key_hex, ctx_hash)
        result = engine.verify_ownership(proof, ctx_hash)
        assert result is True

    def test_wrong_context_fails(self, engine, secret_key_hex):
        proof = engine.prove_ownership(secret_key_hex, b"context_A")
        result = engine.verify_ownership(proof, b"context_B")
        assert result is False


# ── Range proof ───────────────────────────────

class TestRangeProof:
    def test_prove_range(self, engine):
        proof = engine.prove_range(1000, 16, b"ctx")
        assert proof is not None
        assert proof.value_commitment
        assert proof.num_bits == 16

    def test_verify_range(self, engine):
        proof = engine.prove_range(1000, 16, b"ctx")
        result = engine.verify_range(proof, b"ctx")
        assert result is True

    def test_range_proof_various_values(self, engine):
        for val in [0, 1, 255, 65535]:
            proof = engine.prove_range(val, 16, b"ctx")
            assert engine.verify_range(proof, b"ctx") is True


# ── Full validation pipeline ──────────────────

class TestFullPipeline:
    def test_public_pipeline(self, engine):
        ctx = _make_ctx(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx)
        valid, err = engine.validate_envelope_structure(env)
        assert valid is True

    def test_private_roundtrip(self, engine, secret_key_hex):
        ctx = _make_ctx(mode=TransactionMode.PRIVATE, nonce="pipeline_test")
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        env = engine.build_private_envelope(ctx, bundle)

        assert env.mode == TransactionMode.PRIVATE
        assert engine.verify_envelope_integrity(env) is True

        valid, err = engine.validate_envelope_structure(env)
        assert valid is True

    def test_validate_envelope_full(self, engine, secret_key_hex):
        ctx = _make_ctx(mode=TransactionMode.PRIVATE, nonce="full_validate")
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        env = engine.build_private_envelope(ctx, bundle)
        vr, summary = engine.validate_envelope(env)
        assert vr.valid is True
        assert summary.proof_verified is True


# ── Envelope serialization ────────────────────

class TestEnvelopeSerialization:
    def test_json_roundtrip_public(self, engine):
        ctx = _make_ctx(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx)
        j = env.to_json()
        env2 = TransferEnvelope.from_json(j)
        assert env2.mode == TransactionMode.PUBLIC
        assert env2.transaction.amount_lamports == env.transaction.amount_lamports

    def test_json_roundtrip_private(self, engine, secret_key_hex):
        ctx = _make_ctx(mode=TransactionMode.PRIVATE, nonce="ser_test")
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        env = engine.build_private_envelope(ctx, bundle)
        j = env.to_json()
        env2 = TransferEnvelope.from_json(j)
        assert env2.integrity == env.integrity
        assert env2.proof_bundle.binding == env.proof_bundle.binding
