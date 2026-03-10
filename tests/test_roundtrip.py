"""
End-to-end roundtrip test.

Simulates the full online → USB → offline flow:
  1. Online machine: create transaction, select mode, generate proofs
  2. Serialize to JSON (USB transfer)
  3. Offline signer: deserialize, verify proofs + policy, approve/reject
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
from src.privacy.mode import ModeSelector
from src.privacy.policy import SigningPolicyEngine
from src.privacy.validator import PrivacyValidator, ValidationResult


@pytest.fixture
def secret_key_hex():
    return "ab" * 32


def _make_ctx(mode, nonce, amount=1_000_000):
    return TransactionContext(
        unsigned_tx_b64="dHgx",
        from_pubkey="SenderPubkey11111111111111111111111111111111",
        to_pubkey="RecipPubkey11111111111111111111111111111111",
        amount_lamports=amount,
        fee_lamports=5000,
        recent_blockhash="blockhash123",
        mode=mode,
        nonce=nonce,
    )


class TestPublicRoundtrip:
    """Full public-mode flow: online → serialize → offline."""

    def test_public_roundtrip(self):
        # === ONLINE MACHINE ===
        engine = ZkProofEngine()
        ctx = _make_ctx(TransactionMode.PUBLIC, "pub_nonce_1")
        envelope = engine.build_public_envelope(ctx)

        assert envelope.mode == TransactionMode.PUBLIC
        assert envelope.integrity  # HMAC set

        # === USB TRANSFER (serialize to JSON) ===
        json_str = envelope.to_json()

        # === OFFLINE SIGNER ===
        received = TransferEnvelope.from_json(json_str)

        offline_engine = ZkProofEngine()
        assert offline_engine.verify_envelope_integrity(received) is True

        vr, summary = offline_engine.validate_envelope(received)
        assert vr.valid is True


class TestPrivateRoundtrip:
    """Full private-mode flow: online → proofs → serialize → offline verify."""

    def test_private_roundtrip(self, secret_key_hex):
        # === ONLINE MACHINE ===
        engine = ZkProofEngine()
        ctx = _make_ctx(TransactionMode.PRIVATE, "priv_nonce_1", amount=500_000_000)
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        envelope = engine.build_private_envelope(ctx, bundle)

        assert envelope.mode == TransactionMode.PRIVATE
        assert envelope.proof_bundle is not None
        assert envelope.integrity

        # === USB TRANSFER ===
        json_str = envelope.to_json()

        # === OFFLINE SIGNER ===
        received = TransferEnvelope.from_json(json_str)
        offline_engine = ZkProofEngine()

        assert offline_engine.verify_envelope_integrity(received) is True

        vr, summary = offline_engine.validate_envelope(received)
        assert vr.valid is True
        assert summary.proof_verified is True

    def test_private_roundtrip_tampered(self, secret_key_hex):
        """Tampered envelope should fail integrity."""
        engine = ZkProofEngine()
        ctx = _make_ctx(TransactionMode.PRIVATE, "priv_nonce_2", amount=500_000_000)
        bundle = engine.generate_proof_bundle(ctx, secret_key_hex)
        envelope = engine.build_private_envelope(ctx, bundle)

        # Tamper
        envelope.transaction.amount_lamports = 9_999_999_999

        offline_engine = ZkProofEngine()
        assert offline_engine.verify_envelope_integrity(envelope) is False


class TestReplayProtection:
    """Replay detection across transactions within the same engine."""

    def test_replay_detected(self):
        engine = ZkProofEngine()

        # Build two envelopes with same nonce (manually)
        ctx1 = _make_ctx(TransactionMode.PUBLIC, "replay_nonce_1")
        env1 = engine.build_public_envelope(ctx1)

        # First validation should pass
        vr1, _ = engine.validate_envelope(env1)
        assert vr1.valid is True

        # Second validation with same nonce should fail (nonce already seen)
        vr2, _ = engine.validate_envelope(env1)
        # Note: public mode doesn't check nonce freshness in engine,
        # that's handled by the policy engine. Let's test the policy layer.
        policy = SigningPolicyEngine()
        r1 = policy.evaluate(env1)
        assert r1.approved is True
        r2 = policy.evaluate(env1)
        assert r2.approved is False


class TestValidatorPublicFlow:
    def test_validator_public(self):
        validator = PrivacyValidator()
        validator.select_mode("public")
        ctx = _make_ctx(TransactionMode.PUBLIC, "val_pub_1")
        result = validator.validate_transaction(ctx)
        assert result.approved is True
        assert result.mode == TransactionMode.PUBLIC
        assert result.envelope is not None


class TestValidatorPrivateFlow:
    def test_validator_private(self, secret_key_hex):
        validator = PrivacyValidator()
        validator.select_mode("private")
        ctx = _make_ctx(TransactionMode.PRIVATE, "val_priv_1", amount=100_000)
        result = validator.validate_transaction(ctx, secret_key_hex=secret_key_hex)
        assert result.approved is True
        assert result.mode == TransactionMode.PRIVATE
        assert result.proof_bundle is not None
        assert result.envelope is not None

    def test_private_requires_key(self):
        validator = PrivacyValidator()
        validator.select_mode("private")
        ctx = _make_ctx(TransactionMode.PRIVATE, "val_priv_nokey")
        result = validator.validate_transaction(ctx, secret_key_hex=None)
        assert result.approved is False
        assert "secret_key_hex" in result.reason

    def test_mode_mismatch_rejected(self, secret_key_hex):
        validator = PrivacyValidator()
        validator.select_mode("private")
        # Context says public but mode selector says private
        ctx = _make_ctx(TransactionMode.PUBLIC, "mismatch_1")
        result = validator.validate_transaction(ctx, secret_key_hex=secret_key_hex)
        assert result.approved is False
        assert "mismatch" in result.reason.lower()


class TestValidatorNoMode:
    def test_no_mode_rejected(self):
        validator = PrivacyValidator()
        ctx = _make_ctx(TransactionMode.PUBLIC, "no_mode_1")
        result = validator.validate_transaction(ctx)
        assert result.approved is False
        assert "No mode selected" in result.reason
