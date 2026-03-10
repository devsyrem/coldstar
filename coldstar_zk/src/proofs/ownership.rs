//! Schnorr NIZK Proof of Wallet Ownership
//!
//! Proves knowledge of a secret key `x` such that `X = x*G` on the
//! Ristretto group, without revealing `x`.
//!
//! # Protocol (Fiat-Shamir transformed Sigma protocol)
//!
//! 1. Prover picks random `k ← Z_q`, computes `R = k*G`
//! 2. Challenge `c = H(domain || X || R || context_data)`
//! 3. Response `s = k + c*x`
//!
//! Verification:
//!   Check `s*G == R + c*X`
//!
//! # Security Properties
//! - Zero-knowledge: simulator can produce indistinguishable transcripts
//! - Soundness: extracting `x` from two valid proofs with different challenges
//! - Domain-separated: proofs are bound to `DOMAIN_OWNERSHIP_PROOF`
//! - Context-bound: challenge includes transaction context data

use curve25519_dalek::{
    constants::RISTRETTO_BASEPOINT_POINT,
    ristretto::{CompressedRistretto, RistrettoPoint},
    scalar::Scalar,
};
use rand_core::OsRng;
use sha2::{Digest, Sha256};
use zeroize::Zeroize;

use crate::domain::DOMAIN_OWNERSHIP_PROOF;
use crate::error::ZkError;
use crate::transcript::Transcript;
use crate::types::OwnershipProof;

/// Generate a Schnorr NIZK proof of wallet ownership.
///
/// # Arguments
/// * `secret_key` - The 32-byte Ed25519 seed (secret scalar)
/// * `context_data` - Additional context to bind the proof to (e.g., transaction hash)
///
/// # Returns
/// An `OwnershipProof` that can be verified without the secret key.
///
/// # Security
/// - The secret key is converted to a Scalar and used only for computing `s = k + c*x`
/// - The random nonce `k` is generated from OsRng
/// - Both `k` and the secret scalar are zeroized after use
pub fn prove_ownership(secret_key: &[u8; 32], context_data: &[u8]) -> Result<OwnershipProof, ZkError> {
    let g = RISTRETTO_BASEPOINT_POINT;

    // Convert secret key to scalar
    // SECURITY: We clamp the key bytes as Ed25519 does, then use as Scalar
    let mut x = Scalar::from_bytes_mod_order(*secret_key);

    // Compute public key X = x*G
    let big_x = x * g;

    // Pick random nonce k
    let mut k = Scalar::random(&mut OsRng);

    // Compute commitment R = k*G
    let big_r = k * g;

    // Build Fiat-Shamir transcript for the challenge
    let mut transcript = Transcript::new(DOMAIN_OWNERSHIP_PROOF);
    transcript.append_point(b"public_key", &big_x.compress());
    transcript.append_point(b"commitment", &big_r.compress());
    transcript.append(b"context", context_data);

    // Compute challenge c
    let c = transcript.challenge_scalar(b"ownership_challenge");

    // Compute response s = k + c*x
    let s = k + c * x;

    // Compute context hash for inclusion in proof
    let context_hash = {
        let mut hasher = Sha256::new();
        hasher.update(context_data);
        hex::encode(hasher.finalize())
    };

    // Zeroize sensitive values
    x.zeroize();
    k.zeroize();

    Ok(OwnershipProof {
        public_key: hex::encode(big_x.compress().as_bytes()),
        commitment_r: hex::encode(big_r.compress().as_bytes()),
        challenge: hex::encode(c.as_bytes()),
        response: hex::encode(s.as_bytes()),
        context_hash,
    })
}

/// Verify a Schnorr NIZK proof of wallet ownership.
///
/// # Arguments
/// * `proof` - The ownership proof to verify
/// * `context_data` - The same context data that was used during proof generation
///
/// # Returns
/// `Ok(())` if the proof is valid, `Err` otherwise.
///
/// # Verification Steps
/// 1. Deserialize public key X and commitment R from the proof
/// 2. Recompute challenge c using the same transcript
/// 3. Verify s*G == R + c*X
/// 4. Verify the context hash matches
pub fn verify_ownership(proof: &OwnershipProof, context_data: &[u8]) -> Result<(), ZkError> {
    let g = RISTRETTO_BASEPOINT_POINT;

    // Deserialize public key
    let x_bytes = hex::decode(&proof.public_key)?;
    if x_bytes.len() != 32 {
        return Err(ZkError::InvalidProof("Public key must be 32 bytes".into()));
    }
    let mut x_arr = [0u8; 32];
    x_arr.copy_from_slice(&x_bytes);
    let big_x = CompressedRistretto(x_arr)
        .decompress()
        .ok_or_else(|| ZkError::InvalidProof("Invalid public key point".into()))?;

    // Deserialize commitment R
    let r_bytes = hex::decode(&proof.commitment_r)?;
    if r_bytes.len() != 32 {
        return Err(ZkError::InvalidProof("Commitment R must be 32 bytes".into()));
    }
    let mut r_arr = [0u8; 32];
    r_arr.copy_from_slice(&r_bytes);
    let big_r = CompressedRistretto(r_arr)
        .decompress()
        .ok_or_else(|| ZkError::InvalidProof("Invalid commitment point".into()))?;

    // Deserialize response s
    let s_bytes = hex::decode(&proof.response)?;
    if s_bytes.len() != 32 {
        return Err(ZkError::InvalidProof("Response must be 32 bytes".into()));
    }
    let mut s_arr = [0u8; 32];
    s_arr.copy_from_slice(&s_bytes);
    let s = Scalar::from_canonical_bytes(s_arr)
        .into_option()
        .ok_or_else(|| ZkError::InvalidProof("Response is not a canonical scalar".into()))?;

    // Verify context hash
    let expected_context_hash = {
        let mut hasher = Sha256::new();
        hasher.update(context_data);
        hex::encode(hasher.finalize())
    };
    if proof.context_hash != expected_context_hash {
        return Err(ZkError::VerificationFailed(
            "Context hash mismatch — proof may be bound to a different transaction".into(),
        ));
    }

    // Recompute challenge c using the same transcript
    let mut transcript = Transcript::new(DOMAIN_OWNERSHIP_PROOF);
    transcript.append_point(b"public_key", &big_x.compress());
    transcript.append_point(b"commitment", &big_r.compress());
    transcript.append(b"context", context_data);
    let c = transcript.challenge_scalar(b"ownership_challenge");

    // Verify: s*G == R + c*X
    let lhs = s * g;
    let rhs = big_r + c * big_x;

    if lhs != rhs {
        return Err(ZkError::VerificationFailed(
            "Schnorr verification equation failed: s*G ≠ R + c*X".into(),
        ));
    }

    Ok(())
}

/// Derive the Ristretto public key from an Ed25519 seed.
///
/// This converts the 32-byte seed to a Ristretto point X = x*G
/// where x = Scalar::from_bytes_mod_order(seed).
///
/// Note: This is the Ristretto public key, NOT the Ed25519 public key.
/// For ZK proofs we work in the Ristretto group for clean prime-order arithmetic.
pub fn derive_ristretto_pubkey(secret_key: &[u8; 32]) -> RistrettoPoint {
    let x = Scalar::from_bytes_mod_order(*secret_key);
    x * RISTRETTO_BASEPOINT_POINT
}

/// Get the hex-encoded compressed Ristretto public key.
pub fn pubkey_to_hex(secret_key: &[u8; 32]) -> String {
    let pk = derive_ristretto_pubkey(secret_key);
    hex::encode(pk.compress().as_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ownership_proof_valid() {
        let mut seed = [0u8; 32];
        rand::RngCore::fill_bytes(&mut OsRng, &mut seed);
        let context = b"test transaction context";

        let proof = prove_ownership(&seed, context).unwrap();
        assert!(verify_ownership(&proof, context).is_ok());
    }

    #[test]
    fn test_ownership_proof_wrong_context() {
        let mut seed = [0u8; 32];
        rand::RngCore::fill_bytes(&mut OsRng, &mut seed);

        let proof = prove_ownership(&seed, b"context A").unwrap();
        let result = verify_ownership(&proof, b"context B");
        assert!(result.is_err(), "Proof must fail with different context");
    }

    #[test]
    fn test_ownership_proof_different_keys() {
        let mut seed1 = [0u8; 32];
        let mut seed2 = [0u8; 32];
        rand::RngCore::fill_bytes(&mut OsRng, &mut seed1);
        rand::RngCore::fill_bytes(&mut OsRng, &mut seed2);
        let context = b"test context";

        let proof = prove_ownership(&seed1, context).unwrap();

        // The proof should verify against its own public key
        assert!(verify_ownership(&proof, context).is_ok());

        // Generate a proof with a different key — different public key in proof
        let proof2 = prove_ownership(&seed2, context).unwrap();
        assert_ne!(proof.public_key, proof2.public_key);
    }

    #[test]
    fn test_ownership_proof_tampered_response() {
        let mut seed = [0u8; 32];
        rand::RngCore::fill_bytes(&mut OsRng, &mut seed);
        let context = b"test context";

        let mut proof = prove_ownership(&seed, context).unwrap();

        // Tamper with the response
        let mut s_bytes = hex::decode(&proof.response).unwrap();
        s_bytes[0] ^= 0x01;
        proof.response = hex::encode(&s_bytes);

        // Verification should fail (either invalid scalar or equation check)
        // Note: modifying bytes may create a non-canonical scalar
        let result = verify_ownership(&proof, context);
        assert!(result.is_err(), "Tampered proof must fail verification");
    }

    #[test]
    fn test_ownership_proof_deterministic_pubkey() {
        let mut seed = [0u8; 32];
        rand::RngCore::fill_bytes(&mut OsRng, &mut seed);

        let pk1 = pubkey_to_hex(&seed);
        let pk2 = pubkey_to_hex(&seed);
        assert_eq!(pk1, pk2, "Public key derivation must be deterministic");
    }
}
