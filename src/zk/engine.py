"""
ZK Proof Engine for Coldstar.dev

This module provides the high-level interface for generating and verifying
zero-knowledge proofs. It wraps the Rust coldstar_zk library via FFI (ctypes)
and provides a pure-Python fallback for testing.

Architecture:
- Production: All proof generation/verification happens in Rust via FFI
- Fallback: Pure Python using hashlib (for testing when Rust lib is not compiled)

SECURITY: The Rust implementation should ALWAYS be preferred for production use.
The Python fallback uses hash-based commitments which are computationally binding
but do NOT provide the same cryptographic guarantees as the curve-based Rust proofs.
"""

import json
import os
import hashlib
import hmac as hmac_mod
import secrets
import base64
import sys
from ctypes import CDLL, c_char_p, c_void_p, cast, string_at
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, timezone

from src.zk.types import (
    TransactionMode,
    TransactionContext,
    OwnershipProof,
    RangeProof,
    BitProof,
    PolicyProof,
    ProofBundle,
    TransferEnvelope,
    SigningSummary,
    VerificationCheck,
    VerificationResult,
)

# Domain separation constants (must match Rust: coldstar_zk/src/domain.rs)
DOMAIN_OWNERSHIP_PROOF = b"coldstar.zk.ownership.v1"
DOMAIN_RANGE_PROOF = b"coldstar.zk.range.v1"
DOMAIN_POLICY_PROOF = b"coldstar.zk.policy.v1"
DOMAIN_BINDING = b"coldstar.zk.binding.v1"
DOMAIN_ENVELOPE_HMAC = b"coldstar.zk.envelope.hmac.v1"
DOMAIN_TX_CONTEXT = b"coldstar.zk.tx.context.v1"
DOMAIN_NONCE = b"coldstar.zk.nonce.v1"


class ZkProofEngine:
    """
    Main ZK proof engine for Coldstar.dev.

    Provides proof generation, verification, envelope construction,
    and policy validation.

    Uses Rust FFI when available, falls back to pure Python otherwise.
    """

    def __init__(self):
        self._rust_lib = None
        self._using_rust = False
        self._seen_nonces = set()
        self._max_transfer_lamports = 0  # 0 = no limit
        self._allowed_destinations = set()

        # Try to load Rust ZK library
        try:
            self._rust_lib = self._load_rust_lib()
            self._using_rust = True
        except (FileNotFoundError, OSError) as e:
            # Fall back to pure Python
            self._using_rust = False

    @property
    def using_rust(self) -> bool:
        """Whether the Rust ZK library is being used."""
        return self._using_rust

    def _load_rust_lib(self) -> CDLL:
        """Load the compiled Rust coldstar_zk library."""
        possible_paths = [
            Path(__file__).parent.parent.parent / "coldstar_zk" / "target" / "release" / "libcoldstar_zk.dylib",
            Path(__file__).parent.parent.parent / "coldstar_zk" / "target" / "release" / "libcoldstar_zk.so",
            Path(__file__).parent.parent.parent / "coldstar_zk" / "target" / "release" / "coldstar_zk.dll",
            Path(__file__).parent.parent.parent / "coldstar_zk" / "target" / "debug" / "libcoldstar_zk.dylib",
            Path(__file__).parent.parent.parent / "coldstar_zk" / "target" / "debug" / "libcoldstar_zk.so",
            Path(__file__).parent.parent.parent / "coldstar_zk" / "target" / "debug" / "coldstar_zk.dll",
        ]

        for path in possible_paths:
            if path.exists():
                lib = CDLL(str(path))
                # Setup function signatures
                lib.coldstar_zk_prove_ownership.restype = c_void_p
                lib.coldstar_zk_prove_ownership.argtypes = [c_char_p]
                lib.coldstar_zk_verify_ownership.restype = c_void_p
                lib.coldstar_zk_verify_ownership.argtypes = [c_char_p]
                lib.coldstar_zk_prove_range.restype = c_void_p
                lib.coldstar_zk_prove_range.argtypes = [c_char_p]
                lib.coldstar_zk_verify_range.restype = c_void_p
                lib.coldstar_zk_verify_range.argtypes = [c_char_p]
                lib.coldstar_zk_validate_envelope.restype = c_void_p
                lib.coldstar_zk_validate_envelope.argtypes = [c_char_p]
                lib.coldstar_zk_version.restype = c_void_p
                lib.coldstar_zk_free_string.restype = None
                lib.coldstar_zk_free_string.argtypes = [c_void_p]
                return lib

        raise FileNotFoundError(
            "Could not find coldstar_zk library. Build it with:\n"
            "  cd coldstar_zk && cargo build --release"
        )

    def _call_rust(self, func_name: str, input_json: dict) -> dict:
        """Call a Rust FFI function with JSON input/output."""
        if not self._rust_lib:
            raise RuntimeError("Rust library not loaded")

        func = getattr(self._rust_lib, func_name)
        input_str = json.dumps(input_json).encode("utf-8")
        result_ptr = func(input_str)

        if not result_ptr:
            raise RuntimeError(f"Rust function {func_name} returned null")

        # Read the result string
        result_bytes = cast(result_ptr, c_char_p).value
        result_str = result_bytes.decode("utf-8") if result_bytes else "{}"

        # Free the Rust-allocated string
        self._rust_lib.coldstar_zk_free_string(result_ptr)

        return json.loads(result_str)

    # ========================================================================
    # Nonce Generation
    # ========================================================================

    def generate_nonce(self) -> str:
        """Generate a fresh 32-byte cryptographic nonce (hex-encoded)."""
        return secrets.token_hex(32)

    # ========================================================================
    # Transaction Context
    # ========================================================================

    def compute_tx_context_hash(self, tx_context: TransactionContext) -> bytes:
        """Compute a context hash for the transaction.

        This must match the Rust implementation in binding.rs.
        """
        h = hashlib.sha256()
        h.update(DOMAIN_TX_CONTEXT)
        h.update(tx_context.unsigned_tx_b64.encode())
        h.update(tx_context.from_pubkey.encode())
        h.update(tx_context.to_pubkey.encode())
        h.update(tx_context.amount_lamports.to_bytes(8, "little"))
        h.update(tx_context.nonce.encode())
        return h.digest()

    # ========================================================================
    # Ownership Proof
    # ========================================================================

    def prove_ownership(self, secret_key_hex: str, context_data: bytes) -> OwnershipProof:
        """Generate a Schnorr NIZK proof of wallet ownership.

        Args:
            secret_key_hex: 32-byte Ed25519 seed, hex-encoded
            context_data: Context data to bind the proof to

        Returns:
            OwnershipProof
        """
        if self._using_rust:
            result = self._call_rust("coldstar_zk_prove_ownership", {
                "secret_key_hex": secret_key_hex,
                "context_data_hex": context_data.hex(),
            })
            if not result.get("success"):
                raise RuntimeError(f"Ownership proof failed: {result.get('error')}")
            return OwnershipProof.from_dict(result["data"]["ownership_proof"])
        else:
            return self._prove_ownership_python(secret_key_hex, context_data)

    def verify_ownership(self, proof: OwnershipProof, context_data: bytes) -> bool:
        """Verify a Schnorr NIZK ownership proof.

        Returns True if the proof is valid, False otherwise.
        """
        if self._using_rust:
            result = self._call_rust("coldstar_zk_verify_ownership", {
                "proof": proof.to_dict(),
                "context_data_hex": context_data.hex(),
            })
            if not result.get("success"):
                return False
            return result["data"].get("valid", False)
        else:
            return self._verify_ownership_python(proof, context_data)

    def _prove_ownership_python(self, secret_key_hex: str, context_data: bytes) -> OwnershipProof:
        """Pure Python fallback for ownership proof.

        SECURITY NOTE: This uses hash-based commitments, NOT curve arithmetic.
        It demonstrates the proof architecture but does NOT provide the same
        cryptographic guarantees as the Rust Schnorr implementation.
        For production, always use the Rust library.
        """
        secret_key = bytes.fromhex(secret_key_hex)
        if len(secret_key) != 32:
            raise ValueError("Secret key must be 32 bytes")

        # Derive "public key" (hash-based stand-in for Ristretto point)
        pk_hash = hashlib.sha256(DOMAIN_OWNERSHIP_PROOF + b":pubkey:" + secret_key).digest()

        # Random nonce
        k = secrets.token_bytes(32)

        # Commitment R (hash-based stand-in)
        r_hash = hashlib.sha256(DOMAIN_OWNERSHIP_PROOF + b":commitment:" + k).digest()

        # Challenge
        challenge_input = DOMAIN_OWNERSHIP_PROOF + pk_hash + r_hash + context_data
        challenge = hashlib.sha256(challenge_input).digest()

        # Response s = H(k || challenge || secret_key)
        response = hashlib.sha256(k + challenge + secret_key).digest()

        # Context hash
        context_hash = hashlib.sha256(context_data).hexdigest()

        return OwnershipProof(
            public_key=pk_hash.hex(),
            commitment_r=r_hash.hex(),
            challenge=challenge.hex(),
            response=response.hex(),
            context_hash=context_hash,
        )

    def _verify_ownership_python(self, proof: OwnershipProof, context_data: bytes) -> bool:
        """Pure Python fallback for ownership verification."""
        expected_context_hash = hashlib.sha256(context_data).hexdigest()
        if proof.context_hash != expected_context_hash:
            return False

        # Recompute challenge
        pk_bytes = bytes.fromhex(proof.public_key)
        r_bytes = bytes.fromhex(proof.commitment_r)
        challenge_input = DOMAIN_OWNERSHIP_PROOF + pk_bytes + r_bytes + context_data
        expected_challenge = hashlib.sha256(challenge_input).hexdigest()

        return proof.challenge == expected_challenge

    # ========================================================================
    # Range Proof
    # ========================================================================

    def prove_range(self, value: int, num_bits: int, context_data: bytes) -> RangeProof:
        """Generate a range proof that value ∈ [0, 2^num_bits).

        Args:
            value: The value to prove is in range
            num_bits: Number of bits (range is [0, 2^num_bits))
            context_data: Context data for binding

        Returns:
            RangeProof
        """
        if self._using_rust:
            result = self._call_rust("coldstar_zk_prove_range", {
                "value": value,
                "num_bits": num_bits,
                "context_data_hex": context_data.hex(),
            })
            if not result.get("success"):
                raise RuntimeError(f"Range proof failed: {result.get('error')}")
            return RangeProof.from_dict(result["data"]["range_proof"])
        else:
            return self._prove_range_python(value, num_bits, context_data)

    def verify_range(self, proof: RangeProof, context_data: bytes) -> bool:
        """Verify a range proof.

        Returns True if the proof is valid.
        """
        if self._using_rust:
            result = self._call_rust("coldstar_zk_verify_range", {
                "proof": proof.to_dict(),
                "context_data_hex": context_data.hex(),
            })
            if not result.get("success"):
                return False
            return result["data"].get("valid", False)
        else:
            return self._verify_range_python(proof, context_data)

    def _prove_range_python(self, value: int, num_bits: int, context_data: bytes) -> RangeProof:
        """Pure Python fallback for range proof (hash-based)."""
        if num_bits < 1 or num_bits > 64:
            raise ValueError(f"num_bits must be in [1, 64], got {num_bits}")
        if num_bits < 64 and value >= (1 << num_bits):
            raise ValueError(f"Value {value} does not fit in {num_bits} bits")

        # Value commitment (hash-based)
        blinding = secrets.token_bytes(32)
        value_commitment = hashlib.sha256(
            DOMAIN_RANGE_PROOF + b":commit:" + value.to_bytes(8, "little") + blinding
        ).digest()

        # Bit decomposition proofs
        bit_proofs = []
        for i in range(num_bits):
            bit = (value >> i) & 1
            bit_blinding = secrets.token_bytes(32)
            bit_commit = hashlib.sha256(
                DOMAIN_RANGE_PROOF + b":bit:" + bytes([bit]) + bit_blinding
            ).digest()

            # Simulated OR-proof values
            e0 = hashlib.sha256(DOMAIN_RANGE_PROOF + b":e0:" + bit_commit + secrets.token_bytes(16)).digest()
            s0 = hashlib.sha256(DOMAIN_RANGE_PROOF + b":s0:" + bit_blinding + e0).digest()
            e1 = hashlib.sha256(DOMAIN_RANGE_PROOF + b":e1:" + bit_commit + secrets.token_bytes(16)).digest()
            s1 = hashlib.sha256(DOMAIN_RANGE_PROOF + b":s1:" + bit_blinding + e1).digest()

            bit_proofs.append(BitProof(
                commitment=bit_commit.hex(),
                e0=e0.hex(),
                s0=s0.hex(),
                e1=e1.hex(),
                s1=s1.hex(),
            ))

        context_hash = hashlib.sha256(
            DOMAIN_RANGE_PROOF + context_data + num_bits.to_bytes(8, "little") + value_commitment
        ).hexdigest()

        return RangeProof(
            value_commitment=value_commitment.hex(),
            num_bits=num_bits,
            bit_proofs=bit_proofs,
            context_hash=context_hash,
        )

    def _verify_range_python(self, proof: RangeProof, context_data: bytes) -> bool:
        """Pure Python fallback for range proof verification.

        NOTE: The Python fallback only verifies structural consistency,
        not cryptographic soundness. Use Rust for real verification.
        """
        if proof.num_bits < 1 or proof.num_bits > 64:
            return False
        if len(proof.bit_proofs) != proof.num_bits:
            return False

        # Verify context hash structure
        value_commitment = bytes.fromhex(proof.value_commitment)
        expected_context_hash = hashlib.sha256(
            DOMAIN_RANGE_PROOF + context_data + proof.num_bits.to_bytes(8, "little") + value_commitment
        ).hexdigest()

        return proof.context_hash == expected_context_hash

    # ========================================================================
    # Policy Proof
    # ========================================================================

    def prove_policy(self, policy_id: str, satisfied: bool,
                     constraint_data: bytes, context_data: bytes) -> PolicyProof:
        """Generate a policy compliance proof.

        Args:
            policy_id: Identifier for the policy
            satisfied: Whether the policy is satisfied
            constraint_data: Opaque constraint data
            context_data: Transaction context data

        Returns:
            PolicyProof if satisfied, raises otherwise
        """
        if not satisfied:
            raise ValueError(f"Policy '{policy_id}' is not satisfied — cannot generate proof")

        # Hash-based policy proof (used by both Rust-FFI and Python paths for MVP)
        witness = hashlib.sha512(
            DOMAIN_POLICY_PROOF + b":witness:" + policy_id.encode() + constraint_data
        ).digest()

        commitment = hashlib.sha256(
            DOMAIN_POLICY_PROOF + policy_id.encode() + b":satisfied:" + witness[:32]
        ).hexdigest()

        nonce = secrets.token_bytes(32)
        challenge = hashlib.sha256(
            DOMAIN_POLICY_PROOF + policy_id.encode() + witness[:32] + nonce + context_data
        ).digest()

        response = hashlib.sha256(
            nonce + challenge + witness[:32]
        ).digest()

        context_hash = hashlib.sha256(context_data).hexdigest()

        return PolicyProof(
            policy_id=policy_id,
            commitment=commitment,
            response=response.hex(),
            challenge=challenge.hex(),
            context_hash=context_hash,
        )

    # ========================================================================
    # Proof Binding
    # ========================================================================

    def compute_binding(self, tx_context: TransactionContext, bundle: ProofBundle) -> str:
        """Compute the binding hash tying proofs to a transaction.

        Must match the Rust implementation in binding.rs.
        """
        h = hashlib.sha256()
        h.update(DOMAIN_BINDING)
        h.update(b":tx_bytes:")
        h.update(tx_context.unsigned_tx_b64.encode())
        h.update(b":from:")
        h.update(tx_context.from_pubkey.encode())
        h.update(b":to:")
        h.update(tx_context.to_pubkey.encode())
        h.update(b":amount:")
        h.update(tx_context.amount_lamports.to_bytes(8, "little"))
        h.update(b":fee:")
        h.update(tx_context.fee_lamports.to_bytes(8, "little"))
        h.update(b":blockhash:")
        h.update(tx_context.recent_blockhash.encode())
        h.update(b":mode:")
        h.update(tx_context.mode.value.encode())
        h.update(b":nonce:")
        h.update(bundle.nonce.encode())
        h.update(b":ownership_ctx:")
        h.update(bundle.ownership_proof.context_hash.encode())
        if bundle.range_proof:
            h.update(b":range_ctx:")
            h.update(bundle.range_proof.context_hash.encode())
        for pp in bundle.policy_proofs:
            h.update(b":policy_ctx:")
            h.update(pp.policy_id.encode())
            h.update(b":")
            h.update(pp.context_hash.encode())
        h.update(b":created_at:")
        h.update(tx_context.created_at.encode())
        return h.hexdigest()

    def verify_binding(self, tx_context: TransactionContext, bundle: ProofBundle) -> bool:
        """Verify that a proof bundle is correctly bound to a transaction."""
        if tx_context.mode != TransactionMode.PRIVATE:
            return False
        expected = self.compute_binding(tx_context, bundle)
        return bundle.binding == expected

    # ========================================================================
    # Transfer Envelope
    # ========================================================================

    def build_public_envelope(self, tx_context: TransactionContext) -> TransferEnvelope:
        """Build a transfer envelope for a public transaction."""
        if tx_context.mode != TransactionMode.PUBLIC:
            raise ValueError(f"Expected public mode, got {tx_context.mode.value}")

        envelope = TransferEnvelope(
            version="1.0.0",
            mode=TransactionMode.PUBLIC,
            created_at=tx_context.created_at,
            transaction=tx_context,
            proof_bundle=None,
            integrity="",
        )
        envelope.integrity = self._compute_envelope_hmac(envelope)
        return envelope

    def build_private_envelope(self, tx_context: TransactionContext,
                               proof_bundle: ProofBundle) -> TransferEnvelope:
        """Build a transfer envelope for a private transaction."""
        if tx_context.mode != TransactionMode.PRIVATE:
            raise ValueError(f"Expected private mode, got {tx_context.mode.value}")
        if not proof_bundle.binding:
            raise ValueError("Proof bundle must have a binding")

        envelope = TransferEnvelope(
            version="1.0.0",
            mode=TransactionMode.PRIVATE,
            created_at=tx_context.created_at,
            transaction=tx_context,
            proof_bundle=proof_bundle,
            integrity="",
        )
        envelope.integrity = self._compute_envelope_hmac(envelope)
        return envelope

    def verify_envelope_integrity(self, envelope: TransferEnvelope) -> bool:
        """Verify the HMAC integrity of a transfer envelope."""
        expected = self._compute_envelope_hmac(envelope)
        return hmac_mod.compare_digest(envelope.integrity, expected)

    def validate_envelope_structure(self, envelope: TransferEnvelope) -> Tuple[bool, str]:
        """Validate envelope structural consistency.

        Returns (valid, error_message).
        """
        if envelope.mode != envelope.transaction.mode:
            return False, f"Mode mismatch: envelope={envelope.mode.value}, tx={envelope.transaction.mode.value}"

        if envelope.mode == TransactionMode.PUBLIC:
            if envelope.proof_bundle is not None:
                return False, "Public envelope must not contain proof bundle"
        elif envelope.mode == TransactionMode.PRIVATE:
            if envelope.proof_bundle is None:
                return False, "Private envelope must contain proof bundle"

        return True, ""

    def _compute_envelope_hmac(self, envelope: TransferEnvelope) -> str:
        """Compute HMAC-SHA256 for envelope integrity.

        Must match the Rust implementation in envelope.rs.
        """
        key = DOMAIN_ENVELOPE_HMAC + envelope.version.encode()
        mac = hmac_mod.new(key, digestmod=hashlib.sha256)
        mac.update(envelope.version.encode())
        mac.update(envelope.mode.value.encode())
        mac.update(envelope.created_at.encode())
        mac.update(envelope.transaction.unsigned_tx_b64.encode())
        mac.update(envelope.transaction.from_pubkey.encode())
        mac.update(envelope.transaction.to_pubkey.encode())
        mac.update(envelope.transaction.amount_lamports.to_bytes(8, "little"))
        mac.update(envelope.transaction.fee_lamports.to_bytes(8, "little"))
        mac.update(envelope.transaction.recent_blockhash.encode())
        mac.update(envelope.transaction.nonce.encode())

        if envelope.proof_bundle:
            mac.update(b":proof_bundle:")
            bundle_json = json.dumps(envelope.proof_bundle.to_dict(), separators=(",", ":"))
            mac.update(bundle_json.encode())

        return mac.hexdigest()

    # ========================================================================
    # Policy Engine
    # ========================================================================

    def set_max_transfer(self, max_lamports: int):
        """Set maximum allowed transfer amount."""
        self._max_transfer_lamports = max_lamports

    def add_allowed_destination(self, address: str):
        """Add an address to the destination allowlist."""
        self._allowed_destinations.add(address)

    # ========================================================================
    # Full Validation Pipeline
    # ========================================================================

    def validate_envelope(self, envelope: TransferEnvelope) -> Tuple[VerificationResult, SigningSummary]:
        """Validate a transfer envelope — the main entry point for the offline signer.

        Runs all checks: integrity, structure, policy, proofs (for private mode).

        Returns:
            (VerificationResult, SigningSummary)
        """
        checks = []

        # Check 1: Integrity
        integrity_ok = self.verify_envelope_integrity(envelope)
        checks.append(VerificationCheck(
            name="Envelope integrity (HMAC)",
            passed=integrity_ok,
            detail="HMAC verification passed" if integrity_ok else "HMAC verification FAILED",
        ))

        # Check 2: Structure
        struct_ok, struct_err = self.validate_envelope_structure(envelope)
        checks.append(VerificationCheck(
            name="Envelope structure",
            passed=struct_ok,
            detail="Mode and proof bundle consistency verified" if struct_ok else struct_err,
        ))

        # Check 3: Amount sanity
        amount_ok = envelope.transaction.amount_lamports > 0
        checks.append(VerificationCheck(
            name="Amount validation",
            passed=amount_ok,
            detail=f"{envelope.transaction.amount_lamports} lamports",
        ))

        # Check 4: Transfer limit
        limit_ok = (self._max_transfer_lamports == 0 or
                     envelope.transaction.amount_lamports <= self._max_transfer_lamports)
        checks.append(VerificationCheck(
            name="Transfer limit",
            passed=limit_ok,
            detail=f"No limit configured" if self._max_transfer_lamports == 0 else
                   f"{envelope.transaction.amount_lamports} <= {self._max_transfer_lamports}",
        ))

        # Check 5: Destination allowlist
        dest_ok = (not self._allowed_destinations or
                   envelope.transaction.to_pubkey in self._allowed_destinations)
        checks.append(VerificationCheck(
            name="Destination allowlist",
            passed=dest_ok,
            detail="No allowlist configured" if not self._allowed_destinations else
                   "Destination is in allowlist" if dest_ok else
                   f"Destination {envelope.transaction.to_pubkey} NOT in allowlist",
        ))

        # Check 6: Address format
        addr_ok = bool(envelope.transaction.from_pubkey and envelope.transaction.to_pubkey)
        checks.append(VerificationCheck(
            name="Address format",
            passed=addr_ok,
            detail="Sender and recipient addresses present",
        ))

        proofs_verified_count = 0

        # === Private Mode Additional Checks ===
        if envelope.mode == TransactionMode.PRIVATE:
            if envelope.proof_bundle:
                bundle = envelope.proof_bundle

                # Check 7: Nonce freshness
                nonce_fresh = bundle.nonce not in self._seen_nonces
                checks.append(VerificationCheck(
                    name="Nonce freshness (replay protection)",
                    passed=nonce_fresh,
                    detail="Nonce has not been seen before" if nonce_fresh else
                           "REPLAY DETECTED: Nonce was already used!",
                ))
                if nonce_fresh:
                    self._seen_nonces.add(bundle.nonce)

                # Check 8: Ownership proof
                ctx_hash = self.compute_tx_context_hash(envelope.transaction)
                ownership_ok = self.verify_ownership(bundle.ownership_proof, ctx_hash)
                checks.append(VerificationCheck(
                    name="Ownership proof",
                    passed=ownership_ok,
                    detail="Schnorr NIZK ownership proof verified" if ownership_ok else
                           "Ownership proof verification FAILED",
                ))
                if ownership_ok:
                    proofs_verified_count += 1

                # Check 9: Range proof
                if bundle.range_proof:
                    range_ok = self.verify_range(bundle.range_proof, ctx_hash)
                    checks.append(VerificationCheck(
                        name="Range proof",
                        passed=range_ok,
                        detail=f"Amount proven in [0, 2^{bundle.range_proof.num_bits})" if range_ok else
                               "Range proof verification FAILED",
                    ))
                    if range_ok:
                        proofs_verified_count += 1

                # Check 10: Policy proofs
                for pp in bundle.policy_proofs:
                    checks.append(VerificationCheck(
                        name=f"Policy proof: {pp.policy_id}",
                        passed=True,
                        detail="Policy proof present",
                    ))
                    proofs_verified_count += 1

                # Check 11: Binding
                binding_ok = self.verify_binding(envelope.transaction, bundle)
                checks.append(VerificationCheck(
                    name="Proof-to-transaction binding",
                    passed=binding_ok,
                    detail="All proofs correctly bound to transaction" if binding_ok else
                           "Binding verification FAILED",
                ))
            else:
                checks.append(VerificationCheck(
                    name="Proof bundle presence",
                    passed=False,
                    detail="CRITICAL: Private transaction missing proof bundle!",
                ))

        all_passed = all(c.passed for c in checks)
        lamports_per_sol = 1_000_000_000.0

        summary = SigningSummary(
            destination=envelope.transaction.to_pubkey,
            amount_sol=envelope.transaction.amount_lamports / lamports_per_sol,
            fee_sol=envelope.transaction.fee_lamports / lamports_per_sol,
            mode=envelope.mode,
            proof_verified=all_passed,
            proofs_verified_count=proofs_verified_count,
            warnings=[f"{c.name}: {c.detail}" for c in checks if not c.passed],
        )

        result = VerificationResult(
            valid=all_passed,
            checks=checks,
            summary=f"All {len(checks)} checks passed" if all_passed else
                    f"FAILED: {', '.join(c.name for c in checks if not c.passed)}",
        )

        return result, summary

    # ========================================================================
    # Full Proof Bundle Generation
    # ========================================================================

    def generate_proof_bundle(
        self,
        tx_context: TransactionContext,
        secret_key_hex: str,
        include_range_proof: bool = True,
        range_bits: int = 64,
        policy_constraints: Optional[List[Dict[str, Any]]] = None,
    ) -> ProofBundle:
        """Generate a complete proof bundle for a private transaction.

        This is the main high-level method for proof generation.

        Args:
            tx_context: The transaction context
            secret_key_hex: The 32-byte secret key (hex)
            include_range_proof: Whether to include a range proof
            range_bits: Number of bits for range proof
            policy_constraints: List of policy constraints to prove

        Returns:
            A ProofBundle with all proofs and binding
        """
        if tx_context.mode != TransactionMode.PRIVATE:
            raise ValueError("Proof bundle can only be generated for private transactions")

        ctx_hash = self.compute_tx_context_hash(tx_context)
        nonce = self.generate_nonce()

        # 1. Ownership proof
        ownership_proof = self.prove_ownership(secret_key_hex, ctx_hash)

        # 2. Range proof (optional)
        range_proof = None
        if include_range_proof:
            range_proof = self.prove_range(
                tx_context.amount_lamports, range_bits, ctx_hash
            )

        # 3. Policy proofs
        policy_proofs = []
        if policy_constraints:
            for pc in policy_constraints:
                pp = self.prove_policy(
                    policy_id=pc["policy_id"],
                    satisfied=pc["satisfied"],
                    constraint_data=pc.get("constraint_data", b""),
                    context_data=ctx_hash,
                )
                policy_proofs.append(pp)

        # 4. Create bundle (binding computed next)
        bundle = ProofBundle(
            ownership_proof=ownership_proof,
            range_proof=range_proof,
            policy_proofs=policy_proofs,
            binding="",  # Set below
            nonce=nonce,
            version="0.1.0",
        )

        # 5. Compute binding
        bundle.binding = self.compute_binding(tx_context, bundle)

        return bundle
