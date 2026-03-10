"""
Tests for the signing policy engine.

Tests individual checks, mode-specific evaluation,
replay protection, and destination allowlists.
"""

import pytest
from src.privacy.policy import (
    PolicyCheck,
    PolicyCheckResult,
    PolicyEvaluation,
    SigningPolicyEngine,
)
from src.zk.types import (
    OwnershipProof,
    PolicyProof,
    ProofBundle,
    RangeProof,
    TransactionContext,
    TransactionMode,
    TransferEnvelope,
)


def _make_ctx(mode=TransactionMode.PUBLIC, nonce="nonce1", from_pk="Sender11", to_pk="Recip11",
              amount=1_000_000, fee=5000, blockhash="hash1", tx_b64="dHgx"):
    return TransactionContext(
        unsigned_tx_b64=tx_b64,
        from_pubkey=from_pk,
        to_pubkey=to_pk,
        amount_lamports=amount,
        fee_lamports=fee,
        recent_blockhash=blockhash,
        mode=mode,
        nonce=nonce,
    )


def _make_public_envelope(**overrides) -> TransferEnvelope:
    ctx_kwargs = {
        "mode": TransactionMode.PUBLIC,
        "nonce": overrides.pop("nonce", "uniquenonce123"),
        "from_pk": overrides.pop("from_pk", "SenderPubkey1111"),
        "to_pk": overrides.pop("to_pk", "RecipPubkey1111"),
        "amount": overrides.pop("amount", 1_000_000),
    }
    ctx = _make_ctx(**ctx_kwargs)
    return TransferEnvelope(
        version="1.0.0",
        mode=TransactionMode.PUBLIC,
        created_at="2024-01-01T00:00:00Z",
        transaction=ctx,
        proof_bundle=None,
        integrity="",
    )


def _make_private_envelope(binding="abcdef12345", **overrides) -> TransferEnvelope:
    ctx_kwargs = {
        "mode": TransactionMode.PRIVATE,
        "nonce": overrides.pop("nonce", "uniquenonce456"),
        "from_pk": overrides.pop("from_pk", "SenderPubkey1111"),
        "to_pk": overrides.pop("to_pk", "RecipPubkey1111"),
        "amount": overrides.pop("amount", 1_000_000),
    }
    ctx = _make_ctx(**ctx_kwargs)
    bundle = _make_full_bundle(binding=binding)
    return TransferEnvelope(
        version="1.0.0",
        mode=TransactionMode.PRIVATE,
        created_at="2024-01-01T00:00:00Z",
        transaction=ctx,
        proof_bundle=bundle,
        integrity="hmac123",
    )


def _make_full_bundle(binding="abcdef12345") -> ProofBundle:
    return ProofBundle(
        ownership_proof=OwnershipProof("pk", "cmr", "ch", "rsp", "ctx"),
        range_proof=RangeProof("vc", 64, [], "ctx"),
        policy_proofs=[PolicyProof("transfer_limit", "cm", "rsp", "ch", "ctx")],
        binding=binding,
        nonce="bundlenonce1",
    )


# ── Public mode ───────────────────────────────

class TestPublicModePolicy:
    def test_approve_valid(self):
        engine = SigningPolicyEngine()
        env = _make_public_envelope()
        result = engine.evaluate(env)
        assert result.approved is True
        assert result.mode == TransactionMode.PUBLIC

    def test_reject_over_limit(self):
        engine = SigningPolicyEngine(max_transfer_lamports=500_000)
        env = _make_public_envelope(amount=1_000_000)
        result = engine.evaluate(env)
        assert result.approved is False
        assert any(c.name == "amount_limit" and c.result == PolicyCheckResult.FAIL
                    for c in result.checks)

    def test_reject_missing_sender(self):
        engine = SigningPolicyEngine()
        env = _make_public_envelope(from_pk="")
        result = engine.evaluate(env)
        assert result.approved is False

    def test_reject_missing_nonce(self):
        engine = SigningPolicyEngine()
        env = _make_public_envelope(nonce="")
        result = engine.evaluate(env)
        assert result.approved is False

    def test_proof_checks_skipped_public(self):
        engine = SigningPolicyEngine()
        env = _make_public_envelope()
        result = engine.evaluate(env)
        skip_checks = [c for c in result.checks if c.result == PolicyCheckResult.SKIP]
        assert len(skip_checks) >= 1


# ── Private mode ──────────────────────────────

class TestPrivateModePolicy:
    def test_approve_valid(self):
        engine = SigningPolicyEngine()
        env = _make_private_envelope()
        result = engine.evaluate(env)
        assert result.approved is True
        assert result.mode == TransactionMode.PRIVATE

    def test_reject_no_bundle(self):
        engine = SigningPolicyEngine()
        ctx = _make_ctx(mode=TransactionMode.PRIVATE, nonce="n999")
        env = TransferEnvelope(
            version="1.0.0",
            mode=TransactionMode.PRIVATE,
            created_at="2024-01-01T00:00:00Z",
            transaction=ctx,
            proof_bundle=None,
            integrity="",
        )
        result = engine.evaluate(env)
        assert result.approved is False
        assert any(c.name == "proof_bundle_present" and c.result == PolicyCheckResult.FAIL
                    for c in result.checks)

    def test_reject_no_ownership(self):
        engine = SigningPolicyEngine()
        env = _make_private_envelope(nonce="n_own")
        env.proof_bundle.ownership_proof = None
        result = engine.evaluate(env)
        assert result.approved is False

    def test_reject_no_binding(self):
        engine = SigningPolicyEngine()
        env = _make_private_envelope(binding="", nonce="n_bind")
        result = engine.evaluate(env)
        assert result.approved is False


# ── Replay protection ─────────────────────────

class TestReplayProtection:
    def test_nonce_used_once(self):
        engine = SigningPolicyEngine()
        env = _make_public_envelope(nonce="nonce_abc")
        r1 = engine.evaluate(env)
        assert r1.approved is True

        r2 = engine.evaluate(env)  # same nonce
        assert r2.approved is False
        assert any(c.name == "replay" and c.result == PolicyCheckResult.FAIL
                    for c in r2.checks)

    def test_different_nonces_ok(self):
        engine = SigningPolicyEngine()
        r1 = engine.evaluate(_make_public_envelope(nonce="n1"))
        r2 = engine.evaluate(_make_public_envelope(nonce="n2"))
        assert r1.approved is True
        assert r2.approved is True


# ── Destination allowlist ─────────────────────

class TestDestinationAllowlist:
    def test_allowlist_enforced(self):
        engine = SigningPolicyEngine(
            require_destination_allowlist=True,
            allowed_destinations={"AllowedAddr1111"},
        )
        env = _make_public_envelope(to_pk="AllowedAddr1111")
        result = engine.evaluate(env)
        assert result.approved is True

    def test_allowlist_reject_unknown(self):
        engine = SigningPolicyEngine(
            require_destination_allowlist=True,
            allowed_destinations={"AllowedAddr1111"},
        )
        env = _make_public_envelope(to_pk="UnknownAddr1111")
        result = engine.evaluate(env)
        assert result.approved is False

    def test_allowlist_not_enforced(self):
        engine = SigningPolicyEngine(require_destination_allowlist=False)
        env = _make_public_envelope(to_pk="AnyAddr1111")
        result = engine.evaluate(env)
        assert result.approved is True


# ── Display ───────────────────────────────────

class TestPolicyDisplay:
    def test_display_output(self):
        engine = SigningPolicyEngine()
        env = _make_public_envelope()
        result = engine.evaluate(env)
        text = result.display()
        assert "APPROVED" in text
        assert "public" in text.lower()
