"""
ZK Proof Transaction Audit
==========================

Security audit for the ZK proof transaction layer.  Each test corresponds to
a concrete security property that the system is expected to uphold.  Tests are
intentionally self-contained so the audit can be run standalone (no compiled
Rust library required — the Python fallback is exercised throughout).

Audit scope
-----------
1.  Type serialization / de-serialization roundtrips
2.  Transaction mode state-machine lifecycle
3.  Ownership proof generation and verification
4.  Range proof generation and verification (including out-of-range detection)
5.  Envelope HMAC integrity (tamper detection)
6.  Envelope structural validation (mode / proof-bundle consistency)
7.  Proof-to-transaction binding verification
8.  Replay-attack protection (nonce freshness)
9.  Policy engine checks (limits, destination allowlists)
10. Full public transaction pipeline
11. Full private transaction pipeline
12. PrivacyValidator orchestration layer
"""

import secrets
import pytest

from src.zk.types import (
    BitProof,
    OwnershipProof,
    PolicyProof,
    ProofBundle,
    RangeProof,
    SigningSummary,
    TransactionContext,
    TransactionMode,
    TransferEnvelope,
    VerificationCheck,
    VerificationResult,
)
from src.zk.engine import ZkProofEngine
from src.privacy.mode import ModeSelector, ModeState
from src.privacy.policy import PolicyCheckResult, SigningPolicyEngine
from src.privacy.validator import PrivacyValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tx_context(
    mode: TransactionMode = TransactionMode.PUBLIC,
    amount: int = 1_000_000,
    to_pubkey: str = "ReceiverPubkey111111111111111111111111111111",
    from_pubkey: str = "SenderPubkey1111111111111111111111111111111",
) -> TransactionContext:
    return TransactionContext(
        unsigned_tx_b64="dGVzdHR4Ynl0ZXM=",  # base64 "testtxbytes"
        from_pubkey=from_pubkey,
        to_pubkey=to_pubkey,
        amount_lamports=amount,
        fee_lamports=5_000,
        recent_blockhash="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        mode=mode,
        nonce=secrets.token_hex(32),
    )


def _make_engine() -> ZkProofEngine:
    return ZkProofEngine()


_SECRET_KEY_HEX = secrets.token_bytes(32).hex()


# ===========================================================================
# 1. Type serialization / de-serialization roundtrips
# ===========================================================================

class TestTypeSerialization:
    """AUDIT-1: All data types must survive a to_dict / from_dict roundtrip."""

    def test_transaction_mode_from_str_valid(self):
        assert TransactionMode.from_str_strict("public") == TransactionMode.PUBLIC
        assert TransactionMode.from_str_strict("private") == TransactionMode.PRIVATE
        assert TransactionMode.from_str_strict("PUBLIC") == TransactionMode.PUBLIC
        assert TransactionMode.from_str_strict("  Private  ") == TransactionMode.PRIVATE

    def test_transaction_mode_from_str_invalid(self):
        assert TransactionMode.from_str_strict("") is None
        assert TransactionMode.from_str_strict("unknown") is None
        assert TransactionMode.from_str_strict("yes") is None

    def test_transaction_mode_requires_proofs(self):
        assert TransactionMode.PRIVATE.requires_proofs() is True
        assert TransactionMode.PUBLIC.requires_proofs() is False

    def test_transaction_context_roundtrip(self):
        ctx = _make_tx_context()
        d = ctx.to_dict()
        ctx2 = TransactionContext.from_dict(d)
        assert ctx2.from_pubkey == ctx.from_pubkey
        assert ctx2.to_pubkey == ctx.to_pubkey
        assert ctx2.amount_lamports == ctx.amount_lamports
        assert ctx2.fee_lamports == ctx.fee_lamports
        assert ctx2.recent_blockhash == ctx.recent_blockhash
        assert ctx2.mode == ctx.mode
        assert ctx2.nonce == ctx.nonce

    def test_transaction_context_invalid_mode(self):
        ctx = _make_tx_context()
        d = ctx.to_dict()
        d["mode"] = "invalid_mode"
        with pytest.raises(ValueError):
            TransactionContext.from_dict(d)

    def test_ownership_proof_roundtrip(self):
        engine = _make_engine()
        ctx = _make_tx_context()
        ctx_hash = engine.compute_tx_context_hash(ctx)
        proof = engine.prove_ownership(_SECRET_KEY_HEX, ctx_hash)
        d = proof.to_dict()
        proof2 = OwnershipProof.from_dict(d)
        assert proof2.public_key == proof.public_key
        assert proof2.commitment_r == proof.commitment_r
        assert proof2.challenge == proof.challenge
        assert proof2.response == proof.response
        assert proof2.context_hash == proof.context_hash

    def test_range_proof_roundtrip(self):
        engine = _make_engine()
        ctx = _make_tx_context(amount=1_000_000)
        ctx_hash = engine.compute_tx_context_hash(ctx)
        proof = engine.prove_range(1_000_000, 64, ctx_hash)
        d = proof.to_dict()
        proof2 = RangeProof.from_dict(d)
        assert proof2.num_bits == proof.num_bits
        assert proof2.value_commitment == proof.value_commitment
        assert proof2.context_hash == proof.context_hash
        assert len(proof2.bit_proofs) == proof.num_bits

    def test_proof_bundle_roundtrip(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        d = bundle.to_dict()
        bundle2 = ProofBundle.from_dict(d)
        assert bundle2.binding == bundle.binding
        assert bundle2.nonce == bundle.nonce
        assert bundle2.version == bundle.version
        assert bundle2.ownership_proof.public_key == bundle.ownership_proof.public_key

    def test_transfer_envelope_roundtrip_public(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx)
        d = env.to_dict()
        env2 = TransferEnvelope.from_dict(d)
        assert env2.mode == TransactionMode.PUBLIC
        assert env2.proof_bundle is None
        assert env2.integrity == env.integrity

    def test_transfer_envelope_json_roundtrip_private(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)
        json_str = env.to_json()
        env2 = TransferEnvelope.from_json(json_str)
        assert env2.mode == TransactionMode.PRIVATE
        assert env2.proof_bundle is not None
        assert env2.integrity == env.integrity


# ===========================================================================
# 2. Transaction mode state machine
# ===========================================================================

class TestModeStateMachine:
    """AUDIT-2: The mode selector must follow the documented state-machine."""

    def test_initial_state_is_unselected(self):
        sel = ModeSelector()
        assert sel.state == ModeState.UNSELECTED
        assert sel.mode is None

    def test_select_public(self):
        sel = ModeSelector()
        result = sel.select("public")
        assert result.mode == TransactionMode.PUBLIC
        assert sel.state == ModeState.SELECTED

    def test_select_private(self):
        sel = ModeSelector()
        sel.select("private")
        assert sel.mode == TransactionMode.PRIVATE
        assert sel.state == ModeState.SELECTED

    def test_select_invalid_mode_raises(self):
        sel = ModeSelector()
        with pytest.raises(ValueError):
            sel.select("unknown")
        assert sel.state == ModeState.REJECTED

    def test_lock_after_select(self):
        sel = ModeSelector()
        sel.select("public")
        sel.lock()
        assert sel.state == ModeState.LOCKED

    def test_cannot_change_mode_after_lock(self):
        """SECURITY: Locked mode must be immutable."""
        sel = ModeSelector()
        sel.select("public")
        sel.lock()
        with pytest.raises(ValueError, match="Cannot change mode after proof generation"):
            sel.select("private")

    def test_lock_without_select_raises(self):
        sel = ModeSelector()
        with pytest.raises(ValueError):
            sel.lock()

    def test_select_after_rejection_raises(self):
        sel = ModeSelector()
        with pytest.raises(ValueError):
            sel.select("garbage")
        with pytest.raises(ValueError, match="rejected"):
            sel.select("public")

    def test_reset_restores_unselected(self):
        sel = ModeSelector()
        sel.select("private")
        sel.lock()
        sel.reset()
        assert sel.state == ModeState.UNSELECTED
        assert sel.mode is None

    def test_require_mode_matches(self):
        sel = ModeSelector()
        sel.select("private")
        assert sel.require_mode(TransactionMode.PRIVATE) is True

    def test_require_mode_mismatch_raises(self):
        sel = ModeSelector()
        sel.select("public")
        with pytest.raises(ValueError):
            sel.require_mode(TransactionMode.PRIVATE)

    def test_display_status_unselected(self):
        sel = ModeSelector()
        assert "NOT SELECTED" in sel.display_status()

    def test_display_status_locked(self):
        sel = ModeSelector()
        sel.select("private")
        sel.lock()
        assert "LOCKED" in sel.display_status()


# ===========================================================================
# 3. Ownership proof
# ===========================================================================

class TestOwnershipProof:
    """AUDIT-3: Schnorr NIZK ownership proof must verify for genuine keys
    and fail for tampered proofs."""

    def test_ownership_proof_verifies(self):
        engine = _make_engine()
        ctx = _make_tx_context()
        ctx_hash = engine.compute_tx_context_hash(ctx)
        proof = engine.prove_ownership(_SECRET_KEY_HEX, ctx_hash)
        assert engine.verify_ownership(proof, ctx_hash) is True

    def test_ownership_proof_wrong_context_fails(self):
        engine = _make_engine()
        ctx = _make_tx_context()
        ctx_hash = engine.compute_tx_context_hash(ctx)
        proof = engine.prove_ownership(_SECRET_KEY_HEX, ctx_hash)
        other_ctx = b"completely_different_context_data"
        assert engine.verify_ownership(proof, other_ctx) is False

    def test_ownership_proof_tampered_challenge_fails(self):
        engine = _make_engine()
        ctx = _make_tx_context()
        ctx_hash = engine.compute_tx_context_hash(ctx)
        proof = engine.prove_ownership(_SECRET_KEY_HEX, ctx_hash)
        tampered = OwnershipProof(
            public_key=proof.public_key,
            commitment_r=proof.commitment_r,
            challenge="00" * 32,  # zeroed challenge
            response=proof.response,
            context_hash=proof.context_hash,
        )
        assert engine.verify_ownership(tampered, ctx_hash) is False

    def test_ownership_proof_wrong_key_length_raises(self):
        engine = _make_engine()
        ctx_hash = b"context"
        with pytest.raises(ValueError):
            engine.prove_ownership("deadbeef", ctx_hash)  # only 4 bytes

    def test_ownership_proof_context_hash_binds_context(self):
        """Each unique context must produce a unique context_hash."""
        engine = _make_engine()
        ctx_a = b"context_a"
        ctx_b = b"context_b"
        proof_a = engine.prove_ownership(_SECRET_KEY_HEX, ctx_a)
        proof_b = engine.prove_ownership(_SECRET_KEY_HEX, ctx_b)
        assert proof_a.context_hash != proof_b.context_hash


# ===========================================================================
# 4. Range proof
# ===========================================================================

class TestRangeProof:
    """AUDIT-4: Range proofs must accept valid values and reject structural
    violations."""

    def test_range_proof_verifies(self):
        engine = _make_engine()
        ctx = _make_tx_context(amount=500_000)
        ctx_hash = engine.compute_tx_context_hash(ctx)
        proof = engine.prove_range(500_000, 64, ctx_hash)
        assert engine.verify_range(proof, ctx_hash) is True

    def test_range_proof_zero_value(self):
        engine = _make_engine()
        ctx = _make_tx_context(amount=0)
        ctx_hash = engine.compute_tx_context_hash(ctx)
        proof = engine.prove_range(0, 64, ctx_hash)
        assert engine.verify_range(proof, ctx_hash) is True

    def test_range_proof_max_64bit(self):
        engine = _make_engine()
        ctx_hash = b"test_context"
        max_val = (1 << 64) - 1
        proof = engine.prove_range(max_val, 64, ctx_hash)
        assert engine.verify_range(proof, ctx_hash) is True

    def test_range_proof_value_exceeds_bits_raises(self):
        engine = _make_engine()
        ctx_hash = b"test_context"
        with pytest.raises(ValueError, match="does not fit"):
            engine.prove_range(256, 8, ctx_hash)  # 256 doesn't fit in 8 bits

    def test_range_proof_wrong_context_fails(self):
        engine = _make_engine()
        ctx_hash = b"original_context"
        proof = engine.prove_range(100, 64, ctx_hash)
        assert engine.verify_range(proof, b"different_context") is False

    def test_range_proof_wrong_num_bits_fails(self):
        engine = _make_engine()
        ctx_hash = b"test_context"
        proof = engine.prove_range(42, 64, ctx_hash)
        tampered = RangeProof(
            value_commitment=proof.value_commitment,
            num_bits=32,  # wrong
            bit_proofs=proof.bit_proofs,
            context_hash=proof.context_hash,
        )
        assert engine.verify_range(tampered, ctx_hash) is False

    def test_range_proof_truncated_bit_proofs_fails(self):
        engine = _make_engine()
        ctx_hash = b"test_context"
        proof = engine.prove_range(42, 64, ctx_hash)
        tampered = RangeProof(
            value_commitment=proof.value_commitment,
            num_bits=proof.num_bits,
            bit_proofs=proof.bit_proofs[:10],  # truncated
            context_hash=proof.context_hash,
        )
        assert engine.verify_range(tampered, ctx_hash) is False

    def test_range_proof_invalid_num_bits_raises(self):
        engine = _make_engine()
        with pytest.raises(ValueError):
            engine.prove_range(0, 0, b"context")
        with pytest.raises(ValueError):
            engine.prove_range(0, 65, b"context")

    def test_range_proof_bit_count(self):
        engine = _make_engine()
        ctx_hash = b"test_context"
        for bits in (8, 16, 32, 64):
            proof = engine.prove_range(0, bits, ctx_hash)
            assert len(proof.bit_proofs) == bits


# ===========================================================================
# 5. Envelope HMAC integrity (tamper detection)
# ===========================================================================

class TestEnvelopeIntegrity:
    """AUDIT-5: Any modification to the envelope must invalidate its HMAC."""

    def _fresh_public_envelope(self) -> tuple:
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC, amount=1_000_000)
        env = engine.build_public_envelope(ctx)
        return engine, env

    def test_unmodified_envelope_passes(self):
        engine, env = self._fresh_public_envelope()
        assert engine.verify_envelope_integrity(env) is True

    def test_tampered_amount_fails(self):
        """SECURITY: Changing the transfer amount must break HMAC."""
        engine, env = self._fresh_public_envelope()
        env.transaction.amount_lamports += 1
        assert engine.verify_envelope_integrity(env) is False

    def test_tampered_recipient_fails(self):
        """SECURITY: Changing the recipient must break HMAC."""
        engine, env = self._fresh_public_envelope()
        env.transaction.to_pubkey = "EvilRecipient111111111111111111111111111111"
        assert engine.verify_envelope_integrity(env) is False

    def test_tampered_sender_fails(self):
        engine, env = self._fresh_public_envelope()
        env.transaction.from_pubkey = "FakeSender1111111111111111111111111111111111"
        assert engine.verify_envelope_integrity(env) is False

    def test_tampered_fee_fails(self):
        engine, env = self._fresh_public_envelope()
        env.transaction.fee_lamports = 0
        assert engine.verify_envelope_integrity(env) is False

    def test_tampered_mode_fails(self):
        """SECURITY: Mode cannot be silently switched after envelope construction."""
        engine, env = self._fresh_public_envelope()
        env.mode = TransactionMode.PRIVATE
        assert engine.verify_envelope_integrity(env) is False

    def test_tampered_version_fails(self):
        engine, env = self._fresh_public_envelope()
        env.version = "9.9.9"
        assert engine.verify_envelope_integrity(env) is False

    def test_private_envelope_tampered_binding_fails(self):
        """SECURITY: Tampering with proof binding must break HMAC."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)
        assert engine.verify_envelope_integrity(env) is True
        env.proof_bundle.binding = "ff" * 32
        assert engine.verify_envelope_integrity(env) is False


# ===========================================================================
# 6. Envelope structural validation
# ===========================================================================

class TestEnvelopeStructure:
    """AUDIT-6: The engine must reject structurally inconsistent envelopes."""

    def test_public_envelope_no_proof_bundle(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx)
        ok, err = engine.validate_envelope_structure(env)
        assert ok is True

    def test_public_envelope_with_proof_bundle_rejected(self):
        """SECURITY: A public envelope must never carry a proof bundle."""
        engine = _make_engine()
        ctx_pub = _make_tx_context(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx_pub)

        # Inject a fake proof bundle
        ctx_priv = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx_priv, _SECRET_KEY_HEX)
        env.proof_bundle = bundle  # structural violation

        ok, err = engine.validate_envelope_structure(env)
        assert ok is False
        assert "must not contain" in err.lower()

    def test_private_envelope_without_proof_bundle_rejected(self):
        """SECURITY: A private envelope must always carry a proof bundle."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)
        env.proof_bundle = None  # structural violation

        ok, err = engine.validate_envelope_structure(env)
        assert ok is False
        assert "must contain" in err.lower()

    def test_mode_mismatch_rejected(self):
        """SECURITY: envelope.mode != transaction.mode must be rejected."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx)
        env.mode = TransactionMode.PRIVATE  # inject mismatch

        ok, err = engine.validate_envelope_structure(env)
        assert ok is False
        assert "mismatch" in err.lower()

    def test_build_public_envelope_wrong_mode_raises(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        with pytest.raises(ValueError, match="public"):
            engine.build_public_envelope(ctx)

    def test_build_private_envelope_wrong_mode_raises(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        ctx_priv = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx_priv, _SECRET_KEY_HEX)
        with pytest.raises(ValueError, match="private"):
            engine.build_private_envelope(ctx, bundle)


# ===========================================================================
# 7. Proof-to-transaction binding
# ===========================================================================

class TestProofBinding:
    """AUDIT-7: A proof bundle generated for one transaction must not verify
    against a different transaction."""

    def test_binding_valid_for_original_transaction(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        assert engine.verify_binding(ctx, bundle) is True

    def test_binding_fails_for_different_amount(self):
        """SECURITY: Proof generated for 1 SOL must not bind to 2 SOL."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE, amount=1_000_000)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)

        ctx_modified = _make_tx_context(
            mode=TransactionMode.PRIVATE,
            amount=2_000_000,
            to_pubkey=ctx.to_pubkey,
            from_pubkey=ctx.from_pubkey,
        )
        ctx_modified.nonce = ctx.nonce
        ctx_modified.recent_blockhash = ctx.recent_blockhash
        ctx_modified.created_at = ctx.created_at
        assert engine.verify_binding(ctx_modified, bundle) is False

    def test_binding_fails_for_different_recipient(self):
        """SECURITY: Proof generated for recipient A must not bind to recipient B."""
        engine = _make_engine()
        recipient_a = "Recipient1111111111111111111111111111111111"
        recipient_b = "Recipient2222222222222222222222222222222222"
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE, to_pubkey=recipient_a)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)

        ctx_b = _make_tx_context(mode=TransactionMode.PRIVATE, to_pubkey=recipient_b)
        ctx_b.nonce = ctx.nonce
        ctx_b.created_at = ctx.created_at
        assert engine.verify_binding(ctx_b, bundle) is False

    def test_binding_fails_for_public_mode(self):
        """Binding verification is only meaningful for private mode."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)

        ctx_pub = _make_tx_context(mode=TransactionMode.PUBLIC)
        assert engine.verify_binding(ctx_pub, bundle) is False

    def test_binding_fails_tampered_binding_field(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        bundle.binding = "00" * 32
        assert engine.verify_binding(ctx, bundle) is False

    def test_compute_binding_is_deterministic(self):
        """Binding computation must be deterministic (same inputs → same output)."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        b1 = engine.compute_binding(ctx, bundle)
        b2 = engine.compute_binding(ctx, bundle)
        assert b1 == b2


# ===========================================================================
# 8. Replay-attack protection
# ===========================================================================

class TestReplayProtection:
    """AUDIT-8: The same nonce must never be accepted twice."""

    def test_nonce_accepted_first_time(self):
        policy = SigningPolicyEngine()
        ctx = _make_tx_context()
        env = ZkProofEngine().build_public_envelope(ctx)
        result = policy.evaluate(env)
        replay_check = next(c for c in result.checks if c.name == "replay")
        assert replay_check.result == PolicyCheckResult.PASS

    def test_nonce_rejected_second_time(self):
        """SECURITY: A replayed envelope must be rejected by the policy engine."""
        engine = _make_engine()
        policy = SigningPolicyEngine()

        ctx = _make_tx_context()
        env = engine.build_public_envelope(ctx)

        # First evaluation — should pass
        result1 = policy.evaluate(env)
        assert result1.approved is True

        # Second evaluation with same envelope (same nonce) — must fail
        result2 = policy.evaluate(env)
        assert result2.approved is False
        replay_check = next(c for c in result2.checks if c.name == "replay")
        assert replay_check.result == PolicyCheckResult.FAIL
        assert "already used" in replay_check.detail.lower()

    def test_missing_nonce_rejected(self):
        engine = _make_engine()
        policy = SigningPolicyEngine()
        ctx = _make_tx_context()
        env = engine.build_public_envelope(ctx)
        env.transaction.nonce = ""  # wipe nonce

        result = policy.evaluate(env)
        assert result.approved is False

    def test_different_nonces_both_accepted(self):
        engine = _make_engine()
        policy = SigningPolicyEngine()

        ctx1 = _make_tx_context()
        env1 = engine.build_public_envelope(ctx1)

        ctx2 = _make_tx_context()  # fresh nonce via helper
        env2 = engine.build_public_envelope(ctx2)

        assert policy.evaluate(env1).approved is True
        assert policy.evaluate(env2).approved is True

    def test_engine_replay_protection(self):
        """ZkProofEngine's internal nonce tracking must also reject replays."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)

        # First validation — nonce recorded
        result1, _ = engine.validate_envelope(env)
        assert result1.valid is True

        # Second validation — nonce seen before
        result2, _ = engine.validate_envelope(env)
        assert result2.valid is False
        nonce_check = next(
            c for c in result2.checks if "nonce" in c.name.lower()
        )
        assert nonce_check.passed is False


# ===========================================================================
# 9. Policy engine checks
# ===========================================================================

class TestPolicyEngine:
    """AUDIT-9: The policy engine must enforce transfer limits and allowlists."""

    def test_amount_within_limit_passes(self):
        engine = _make_engine()
        policy = SigningPolicyEngine(max_transfer_lamports=10_000_000)
        ctx = _make_tx_context(amount=5_000_000)
        env = engine.build_public_envelope(ctx)
        result = policy.evaluate(env)
        amt_check = next(c for c in result.checks if c.name == "amount_limit")
        assert amt_check.result == PolicyCheckResult.PASS

    def test_amount_exceeds_limit_fails(self):
        """SECURITY: Transfers above the configured limit must be blocked."""
        engine = _make_engine()
        policy = SigningPolicyEngine(max_transfer_lamports=1_000_000)
        ctx = _make_tx_context(amount=2_000_000)
        env = engine.build_public_envelope(ctx)
        result = policy.evaluate(env)
        assert result.approved is False
        amt_check = next(c for c in result.checks if c.name == "amount_limit")
        assert amt_check.result == PolicyCheckResult.FAIL

    def test_destination_in_allowlist_passes(self):
        allowed = "AllowedRecipient111111111111111111111111111"
        engine = _make_engine()
        policy = SigningPolicyEngine(
            allowed_destinations={allowed},
            require_destination_allowlist=True,
        )
        ctx = _make_tx_context(to_pubkey=allowed)
        env = engine.build_public_envelope(ctx)
        result = policy.evaluate(env)
        dest_check = next(c for c in result.checks if c.name == "destination")
        assert dest_check.result == PolicyCheckResult.PASS

    def test_destination_not_in_allowlist_fails(self):
        """SECURITY: Transfers to non-allowlisted addresses must be blocked."""
        engine = _make_engine()
        policy = SigningPolicyEngine(
            allowed_destinations={"AllowedOnly1111111111111111111111111111111"},
            require_destination_allowlist=True,
        )
        ctx = _make_tx_context(to_pubkey="UnknownRecipient1111111111111111111111111")
        env = engine.build_public_envelope(ctx)
        result = policy.evaluate(env)
        assert result.approved is False
        dest_check = next(c for c in result.checks if c.name == "destination")
        assert dest_check.result == PolicyCheckResult.FAIL

    def test_empty_allowlist_with_enforcement_fails(self):
        """An enforced but empty allowlist must block all destinations."""
        engine = _make_engine()
        policy = SigningPolicyEngine(
            allowed_destinations=set(),
            require_destination_allowlist=True,
        )
        ctx = _make_tx_context()
        env = engine.build_public_envelope(ctx)
        result = policy.evaluate(env)
        assert result.approved is False

    def test_no_allowlist_enforcement_skipped(self):
        engine = _make_engine()
        policy = SigningPolicyEngine(require_destination_allowlist=False)
        ctx = _make_tx_context(to_pubkey="AnyAddress1111111111111111111111111111111")
        env = engine.build_public_envelope(ctx)
        result = policy.evaluate(env)
        dest_check = next(c for c in result.checks if c.name == "destination")
        assert dest_check.result == PolicyCheckResult.PASS

    def test_private_mode_requires_proof_bundle(self):
        """SECURITY: Private envelope without a proof bundle must be rejected."""
        engine = _make_engine()
        policy = SigningPolicyEngine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)
        env.proof_bundle = None  # strip bundle

        result = policy.evaluate(env)
        assert result.approved is False

    def test_missing_sender_fails_structure(self):
        engine = _make_engine()
        policy = SigningPolicyEngine()
        ctx = _make_tx_context(from_pubkey="")
        env = engine.build_public_envelope(ctx)
        result = policy.evaluate(env)
        assert result.approved is False

    def test_missing_recipient_fails_structure(self):
        engine = _make_engine()
        policy = SigningPolicyEngine()
        ctx = _make_tx_context(to_pubkey="")
        env = engine.build_public_envelope(ctx)
        result = policy.evaluate(env)
        assert result.approved is False

    def test_set_max_transfer(self):
        engine = _make_engine()
        policy = SigningPolicyEngine(max_transfer_lamports=100)
        policy.set_max_transfer(5_000_000)
        ctx = _make_tx_context(amount=4_000_000)
        env = engine.build_public_envelope(ctx)
        assert policy.evaluate(env).approved is True

    def test_add_remove_allowed_destination(self):
        addr = "DynamicRecipient111111111111111111111111111"
        engine = _make_engine()
        policy = SigningPolicyEngine(require_destination_allowlist=True)
        policy.add_allowed_destination(addr)
        ctx = _make_tx_context(to_pubkey=addr)
        env = engine.build_public_envelope(ctx)
        assert policy.evaluate(env).approved is True

        # Remove and verify it is now blocked
        policy2 = SigningPolicyEngine(
            allowed_destinations={addr},
            require_destination_allowlist=True,
        )
        policy2.remove_allowed_destination(addr)
        ctx2 = _make_tx_context(to_pubkey=addr)
        env2 = engine.build_public_envelope(ctx2)
        assert policy2.evaluate(env2).approved is False


# ===========================================================================
# 10. Full public transaction pipeline
# ===========================================================================

class TestPublicPipeline:
    """AUDIT-10: End-to-end public mode transaction must pass all validation."""

    def test_full_public_pipeline(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC, amount=500_000)
        env = engine.build_public_envelope(ctx)

        vr, summary = engine.validate_envelope(env)

        assert vr.valid is True
        assert all(c.passed for c in vr.checks)
        assert summary.mode == TransactionMode.PUBLIC
        assert summary.proof_verified is True
        assert summary.proofs_verified_count == 0  # no ZK proofs in public mode

    def test_public_pipeline_signing_summary_values(self):
        engine = _make_engine()
        amount = 2_000_000_000  # 2 SOL
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC, amount=amount)
        env = engine.build_public_envelope(ctx)
        _, summary = engine.validate_envelope(env)

        assert abs(summary.amount_sol - 2.0) < 1e-9
        assert summary.destination == ctx.to_pubkey

    def test_public_pipeline_tamper_detected(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        env = engine.build_public_envelope(ctx)
        env.transaction.amount_lamports += 99_999  # tamper

        vr, _ = engine.validate_envelope(env)
        assert vr.valid is False
        integrity_check = next(c for c in vr.checks if "integrity" in c.name.lower())
        assert integrity_check.passed is False


# ===========================================================================
# 11. Full private transaction pipeline
# ===========================================================================

class TestPrivatePipeline:
    """AUDIT-11: End-to-end private mode transaction must generate valid ZK
    proofs and pass all validation checks."""

    def test_full_private_pipeline(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE, amount=1_000_000)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)

        vr, summary = engine.validate_envelope(env)

        assert vr.valid is True, f"Failed: {vr.summary}"
        assert summary.mode == TransactionMode.PRIVATE
        assert summary.proofs_verified_count >= 1  # ownership at minimum

    def test_private_pipeline_ownership_verified(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)

        vr, _ = engine.validate_envelope(env)
        ownership_check = next(
            c for c in vr.checks if c.name == "Ownership proof"
        )
        assert ownership_check.passed is True

    def test_private_pipeline_range_proof_verified(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)

        vr, _ = engine.validate_envelope(env)
        range_check = next(
            (c for c in vr.checks if c.name == "Range proof"), None
        )
        assert range_check is not None
        assert range_check.passed is True

    def test_private_pipeline_binding_verified(self):
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)

        vr, _ = engine.validate_envelope(env)
        binding_check = next(
            c for c in vr.checks if "binding" in c.name.lower()
        )
        assert binding_check.passed is True

    def test_private_pipeline_tamper_amount_detected(self):
        """SECURITY: Modifying the amount after proof generation must fail."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE, amount=1_000_000)
        bundle = engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)
        env = engine.build_private_envelope(ctx, bundle)

        env.transaction.amount_lamports = 999_000_000  # tamper

        vr, _ = engine.validate_envelope(env)
        assert vr.valid is False

    def test_generate_proof_bundle_public_mode_raises(self):
        """Proof bundles must not be generated for public mode transactions."""
        engine = _make_engine()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        with pytest.raises(ValueError, match="private"):
            engine.generate_proof_bundle(ctx, _SECRET_KEY_HEX)


# ===========================================================================
# 12. PrivacyValidator orchestration layer
# ===========================================================================

class TestPrivacyValidator:
    """AUDIT-12: The PrivacyValidator orchestrates the full pipeline; validate
    that it enforces mode selection and delegates correctly."""

    def test_no_mode_selected_rejected(self):
        validator = PrivacyValidator()
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        result = validator.validate_transaction(ctx)
        assert result.approved is False
        assert "no mode selected" in result.reason.lower()

    def test_public_mode_approved(self):
        validator = PrivacyValidator()
        validator.select_mode("public")
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        result = validator.validate_transaction(ctx)
        assert result.approved is True
        assert result.mode == TransactionMode.PUBLIC

    def test_private_mode_approved(self):
        validator = PrivacyValidator()
        validator.select_mode("private")
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        result = validator.validate_transaction(ctx, secret_key_hex=_SECRET_KEY_HEX)
        assert result.approved is True
        assert result.mode == TransactionMode.PRIVATE

    def test_private_mode_without_key_rejected(self):
        validator = PrivacyValidator()
        validator.select_mode("private")
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        result = validator.validate_transaction(ctx)  # no key provided
        assert result.approved is False
        assert "secret_key_hex" in result.reason.lower()

    def test_mode_mismatch_rejected(self):
        """Context mode must match the selected mode."""
        validator = PrivacyValidator()
        validator.select_mode("public")
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)  # mismatch
        result = validator.validate_transaction(ctx, secret_key_hex=_SECRET_KEY_HEX)
        assert result.approved is False
        assert "mismatch" in result.reason.lower()

    def test_mode_locked_after_public_validation(self):
        validator = PrivacyValidator()
        validator.select_mode("public")
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        validator.validate_transaction(ctx)
        assert validator.mode_state == ModeState.LOCKED

    def test_mode_locked_after_private_validation(self):
        validator = PrivacyValidator()
        validator.select_mode("private")
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        validator.validate_transaction(ctx, secret_key_hex=_SECRET_KEY_HEX)
        assert validator.mode_state == ModeState.LOCKED

    def test_reset_allows_new_transaction(self):
        validator = PrivacyValidator()
        validator.select_mode("public")
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        validator.validate_transaction(ctx)

        validator.reset()
        assert validator.mode_state == ModeState.UNSELECTED

        validator.select_mode("public")
        ctx2 = _make_tx_context(mode=TransactionMode.PUBLIC)
        result = validator.validate_transaction(ctx2)
        assert result.approved is True

    def test_verify_envelope_offline_public(self):
        """Simulates the offline signer verifying a public envelope."""
        validator = PrivacyValidator()
        validator.select_mode("public")
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        tx_result = validator.validate_transaction(ctx)

        # Offline signer verifies
        offline_validator = PrivacyValidator()
        verify_result = offline_validator.verify_envelope(tx_result.envelope)
        assert verify_result.approved is True

    def test_verify_envelope_offline_private(self):
        """Simulates the offline signer verifying a private envelope."""
        validator = PrivacyValidator()
        validator.select_mode("private")
        ctx = _make_tx_context(mode=TransactionMode.PRIVATE)
        tx_result = validator.validate_transaction(ctx, secret_key_hex=_SECRET_KEY_HEX)

        offline_validator = PrivacyValidator()
        verify_result = offline_validator.verify_envelope(tx_result.envelope)
        assert verify_result.approved is True

    def test_verify_tampered_envelope_rejected(self):
        """SECURITY: Offline signer must reject a tampered envelope."""
        validator = PrivacyValidator()
        validator.select_mode("public")
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        tx_result = validator.validate_transaction(ctx)

        # Tamper with the amount in transit
        tx_result.envelope.transaction.amount_lamports += 1_000_000

        offline_validator = PrivacyValidator()
        verify_result = offline_validator.verify_envelope(tx_result.envelope)
        assert verify_result.approved is False

    def test_transfer_limit_enforced_via_validator(self):
        validator = PrivacyValidator(max_transfer_lamports=1_000_000)
        validator.select_mode("public")
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC, amount=5_000_000)
        result = validator.validate_transaction(ctx)
        assert result.approved is False

    def test_signing_summary_present_after_validation(self):
        validator = PrivacyValidator()
        validator.select_mode("public")
        ctx = _make_tx_context(mode=TransactionMode.PUBLIC)
        result = validator.validate_transaction(ctx)
        assert result.signing_summary is not None
        assert result.policy_evaluation is not None
