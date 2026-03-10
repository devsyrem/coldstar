//! Range Proof — proving a committed value lies in [0, 2^n).
//!
//! Uses bit decomposition with per-bit Sigma OR-proofs (CDS technique).
//!
//! # Protocol
//!
//! Given a Pedersen commitment C = v*G + r*H, prove v ∈ [0, 2^n):
//!
//! 1. Decompose v into bits: v = Σ(b_i * 2^i) for i = 0..n-1
//! 2. For each bit b_i:
//!    a. Choose random blinding r_i, compute C_i = b_i*G + r_i*H
//!    b. Prove b_i ∈ {0, 1} using a 1-of-2 Sigma OR-proof:
//!       - Branch 0: prove C_i commits to 0 (know r_i s.t. C_i = r_i*H)
//!       - Branch 1: prove C_i - G commits to 0 (know r_i s.t. C_i - G = r_i*H)
//! 3. Prove consistency: Σ(2^i * C_i) == C
//!    This is ensured by choosing r = Σ(2^i * r_i)
//!
//! # Sigma OR-proof (CDS technique) for bit b_i:
//!
//! If b_i = 0 (real branch: C_i = r_i*H):
//!   - Simulate branch 1: pick random e1, s1, compute R1 = s1*H + e1*(C_i - G)
//!   - Real branch 0: pick random k0, compute R0 = k0*H
//!   - Challenge e = H(transcript || C_i || R0 || R1)
//!   - e0 = e - e1
//!   - s0 = k0 - e0*r_i
//!   - Output: (e0, s0, e1, s1)
//!
//! If b_i = 1 (real branch: C_i - G = r_i*H):
//!   - Simulate branch 0: pick random e0, s0, compute R0 = s0*H + e0*C_i
//!   - Real branch 1: pick random k1, compute R1 = k1*H
//!   - Challenge e = H(transcript || C_i || R0 || R1)
//!   - e1 = e - e0
//!   - s1 = k1 - e1*r_i
//!   - Output: (e0, s0, e1, s1)
//!
//! Verification (for each bit):
//!   - R0 = s0*H + e0*C_i
//!   - R1 = s1*H + e1*(C_i - G)
//!   - Check e0 + e1 == H(transcript || C_i || R0 || R1)
//!
//! # Proof Size
//! O(n) where n = number of bits. Each bit adds ~160 bytes.
//! For 64-bit values: ~10KB. Acceptable for USB transfer.

use curve25519_dalek::{
    ristretto::RistrettoPoint,
    scalar::Scalar,
};
use rand_core::OsRng;
use zeroize::Zeroize;

use crate::commitment::{commit, commitment_from_hex, commitment_to_hex, generator_g, generator_h};
use crate::domain::{DOMAIN_RANGE_OR_PROOF, DOMAIN_RANGE_PROOF, MAX_RANGE_BITS};
use crate::error::ZkError;
use crate::transcript::Transcript;
use crate::types::{BitProof, RangeProof};

/// Generate a range proof that a value v lies in [0, 2^num_bits).
///
/// # Arguments
/// * `value` - The value to prove is in range
/// * `num_bits` - The number of bits (range is [0, 2^num_bits))
/// * `context_data` - Context data to bind the proof to
///
/// # Returns
/// A tuple of (RangeProof, blinding_factor) where the blinding factor
/// is the opening of the value commitment. The caller should store the
/// blinding factor securely if they need to open the commitment later.
pub fn prove_range(
    value: u64,
    num_bits: usize,
    context_data: &[u8],
) -> Result<(RangeProof, Scalar), ZkError> {
    if num_bits == 0 || num_bits > MAX_RANGE_BITS {
        return Err(ZkError::RangeError(format!(
            "num_bits must be in [1, {}], got {}",
            MAX_RANGE_BITS, num_bits
        )));
    }

    // Check value is in range
    if num_bits < 64 && value >= (1u64 << num_bits) {
        return Err(ZkError::RangeError(format!(
            "Value {} does not fit in {} bits",
            value, num_bits
        )));
    }

    let g = generator_g();
    let h = generator_h();

    // Decompose value into bits
    let bits: Vec<u8> = (0..num_bits).map(|i| ((value >> i) & 1) as u8).collect();

    // Generate random blinding factors for each bit
    let mut bit_blindings: Vec<Scalar> = (0..num_bits)
        .map(|_| Scalar::random(&mut OsRng))
        .collect();

    // The total blinding factor for the value commitment
    // must satisfy: r = Σ(2^i * r_i) so that Σ(2^i * C_i) = C
    let mut total_blinding = Scalar::ZERO;
    let mut power_of_two = Scalar::ONE;
    let two = Scalar::from(2u64);
    for r_i in &bit_blindings {
        total_blinding += power_of_two * r_i;
        power_of_two *= two;
    }

    // Compute value commitment C = v*G + r*H
    let v_scalar = Scalar::from(value);
    let value_commitment = commit(&v_scalar, &total_blinding);

    // Generate per-bit proofs
    let mut bit_proofs = Vec::with_capacity(num_bits);

    // Build outer transcript for context
    let context_hash = {
        let mut t = Transcript::new(DOMAIN_RANGE_PROOF);
        t.append(b"context", context_data);
        t.append(b"num_bits", &(num_bits as u64).to_le_bytes());
        t.append_point(b"value_commitment", &value_commitment.compress());
        hex::encode(&t.digest()[..32])
    };

    for i in 0..num_bits {
        let b_i = bits[i];
        let r_i = bit_blindings[i];

        // Bit commitment: C_i = b_i*G + r_i*H
        let c_i = Scalar::from(b_i as u64) * g + r_i * h;

        let bit_proof = prove_bit(b_i, r_i, c_i, g, h, i, context_data)?;
        bit_proofs.push(bit_proof);
    }

    // Zeroize sensitive data
    for r in &mut bit_blindings {
        r.zeroize();
    }

    Ok((
        RangeProof {
            value_commitment: commitment_to_hex(&value_commitment),
            num_bits,
            bit_proofs,
            context_hash,
        },
        total_blinding,
    ))
}

/// Generate a Sigma OR-proof that a bit commitment contains 0 or 1.
///
/// SECURITY: This is the core cryptographic primitive of the range proof.
/// The CDS technique ensures zero-knowledge: the verifier cannot tell
/// which branch (0 or 1) is the real one.
fn prove_bit(
    bit: u8,
    blinding: Scalar,
    c_i: RistrettoPoint,
    g: RistrettoPoint,
    h: RistrettoPoint,
    bit_index: usize,
    context_data: &[u8],
) -> Result<BitProof, ZkError> {
    if bit > 1 {
        return Err(ZkError::RangeError("Bit must be 0 or 1".into()));
    }

    let (e0, s0, e1, s1) = if bit == 0 {
        // Real branch: b=0, so C_i = 0*G + r_i*H = r_i*H
        // We know r_i such that C_i = r_i*H

        // Simulate branch 1 (b=1): pick random e1, s1
        let e1_sim = Scalar::random(&mut OsRng);
        let s1_sim = Scalar::random(&mut OsRng);
        // R1 = s1*H + e1*(C_i - G) [simulated transcript]
        let r1_sim = s1_sim * h + e1_sim * (c_i - g);

        // Real branch 0: pick random k0
        let mut k0 = Scalar::random(&mut OsRng);
        let r0_real = k0 * h;

        // Compute challenge e = H(transcript)
        let mut transcript = Transcript::new(DOMAIN_RANGE_OR_PROOF);
        transcript.append(b"context", context_data);
        transcript.append(b"bit_index", &(bit_index as u64).to_le_bytes());
        transcript.append_point(b"C_i", &c_i.compress());
        transcript.append_point(b"R0", &r0_real.compress());
        transcript.append_point(b"R1", &r1_sim.compress());
        let e = transcript.challenge_scalar(b"bit_challenge");

        // e0 = e - e1
        let e0_real = e - e1_sim;
        // s0 = k0 - e0*r_i
        let s0_real = k0 - e0_real * blinding;

        k0.zeroize();

        (e0_real, s0_real, e1_sim, s1_sim)
    } else {
        // Real branch: b=1, so C_i = 1*G + r_i*H = G + r_i*H
        // We know r_i such that C_i - G = r_i*H

        // Simulate branch 0 (b=0): pick random e0, s0
        let e0_sim = Scalar::random(&mut OsRng);
        let s0_sim = Scalar::random(&mut OsRng);
        // R0 = s0*H + e0*C_i [simulated transcript]
        let r0_sim = s0_sim * h + e0_sim * c_i;

        // Real branch 1: pick random k1
        let mut k1 = Scalar::random(&mut OsRng);
        let r1_real = k1 * h;

        // Compute challenge e = H(transcript)
        let mut transcript = Transcript::new(DOMAIN_RANGE_OR_PROOF);
        transcript.append(b"context", context_data);
        transcript.append(b"bit_index", &(bit_index as u64).to_le_bytes());
        transcript.append_point(b"C_i", &c_i.compress());
        transcript.append_point(b"R0", &r0_sim.compress());
        transcript.append_point(b"R1", &r1_real.compress());
        let e = transcript.challenge_scalar(b"bit_challenge");

        // e1 = e - e0
        let e1_real = e - e0_sim;
        // s1 = k1 - e1*r_i
        let s1_real = k1 - e1_real * blinding;

        k1.zeroize();

        (e0_sim, s0_sim, e1_real, s1_real)
    };

    Ok(BitProof {
        commitment: commitment_to_hex(&c_i),
        e0: hex::encode(e0.as_bytes()),
        s0: hex::encode(s0.as_bytes()),
        e1: hex::encode(e1.as_bytes()),
        s1: hex::encode(s1.as_bytes()),
    })
}

/// Verify a range proof.
///
/// # Arguments
/// * `proof` - The range proof to verify
/// * `context_data` - The same context data used during proof generation
///
/// # Verification Steps
/// 1. For each bit proof: verify the Sigma OR-proof
/// 2. Verify consistency: Σ(2^i * C_i) == C (value commitment)
pub fn verify_range(proof: &RangeProof, context_data: &[u8]) -> Result<(), ZkError> {
    if proof.num_bits == 0 || proof.num_bits > MAX_RANGE_BITS {
        return Err(ZkError::RangeError(format!(
            "Invalid num_bits: {}",
            proof.num_bits
        )));
    }

    if proof.bit_proofs.len() != proof.num_bits {
        return Err(ZkError::RangeError(format!(
            "Expected {} bit proofs, got {}",
            proof.num_bits,
            proof.bit_proofs.len()
        )));
    }

    let g = generator_g();
    let h = generator_h();

    // Deserialize value commitment
    let value_commitment = commitment_from_hex(&proof.value_commitment)?;

    // Verify context hash
    let expected_context_hash = {
        let mut t = Transcript::new(DOMAIN_RANGE_PROOF);
        t.append(b"context", context_data);
        t.append(b"num_bits", &(proof.num_bits as u64).to_le_bytes());
        t.append_point(b"value_commitment", &value_commitment.compress());
        hex::encode(&t.digest()[..32])
    };
    if proof.context_hash != expected_context_hash {
        return Err(ZkError::VerificationFailed(
            "Range proof context hash mismatch".into(),
        ));
    }

    // Verify each bit proof and accumulate bit commitments
    let mut accumulated = RistrettoPoint::default(); // identity
    let mut power_of_two = Scalar::ONE;
    let two = Scalar::from(2u64);

    for (i, bit_proof) in proof.bit_proofs.iter().enumerate() {
        // Deserialize bit commitment C_i
        let c_i = commitment_from_hex(&bit_proof.commitment)?;

        // Verify the OR-proof for this bit
        verify_bit_proof(bit_proof, c_i, g, h, i, context_data)?;

        // Accumulate: sum += 2^i * C_i
        accumulated += power_of_two * c_i;
        power_of_two *= two;
    }

    // Verify consistency: Σ(2^i * C_i) == value_commitment
    if accumulated != value_commitment {
        return Err(ZkError::VerificationFailed(
            "Range proof consistency check failed: Σ(2^i * C_i) ≠ C".into(),
        ));
    }

    Ok(())
}

/// Verify a single bit OR-proof.
///
/// Checks that the committed value is either 0 or 1 using the CDS technique.
fn verify_bit_proof(
    proof: &BitProof,
    c_i: RistrettoPoint,
    g: RistrettoPoint,
    h: RistrettoPoint,
    bit_index: usize,
    context_data: &[u8],
) -> Result<(), ZkError> {
    // Deserialize scalars
    let e0 = deserialize_scalar(&proof.e0, "e0")?;
    let s0 = deserialize_scalar(&proof.s0, "s0")?;
    let e1 = deserialize_scalar(&proof.e1, "e1")?;
    let s1 = deserialize_scalar(&proof.s1, "s1")?;

    // Recompute R0 = s0*H + e0*C_i
    let r0 = s0 * h + e0 * c_i;

    // Recompute R1 = s1*H + e1*(C_i - G)
    let r1 = s1 * h + e1 * (c_i - g);

    // Recompute challenge
    let mut transcript = Transcript::new(DOMAIN_RANGE_OR_PROOF);
    transcript.append(b"context", context_data);
    transcript.append(b"bit_index", &(bit_index as u64).to_le_bytes());
    transcript.append_point(b"C_i", &c_i.compress());
    transcript.append_point(b"R0", &r0.compress());
    transcript.append_point(b"R1", &r1.compress());
    let e = transcript.challenge_scalar(b"bit_challenge");

    // Check: e0 + e1 == e
    if e0 + e1 != e {
        return Err(ZkError::VerificationFailed(format!(
            "Bit proof {} failed: e0 + e1 ≠ e",
            bit_index
        )));
    }

    Ok(())
}

/// Helper to deserialize a scalar from hex.
fn deserialize_scalar(hex_str: &str, name: &str) -> Result<Scalar, ZkError> {
    let bytes = hex::decode(hex_str)?;
    if bytes.len() != 32 {
        return Err(ZkError::InvalidProof(format!(
            "{} must be 32 bytes, got {}",
            name,
            bytes.len()
        )));
    }
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&bytes);
    // Use from_bytes_mod_order for robustness — accepts any 32 bytes
    Ok(Scalar::from_bytes_mod_order(arr))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_range_proof_zero() {
        let (proof, _blinding) = prove_range(0, 8, b"test").unwrap();
        assert!(verify_range(&proof, b"test").is_ok());
    }

    #[test]
    fn test_range_proof_one() {
        let (proof, _blinding) = prove_range(1, 8, b"test").unwrap();
        assert!(verify_range(&proof, b"test").is_ok());
    }

    #[test]
    fn test_range_proof_max_8bit() {
        let (proof, _blinding) = prove_range(255, 8, b"test").unwrap();
        assert!(verify_range(&proof, b"test").is_ok());
    }

    #[test]
    fn test_range_proof_random_value() {
        let value: u64 = rand::random::<u32>() as u64;
        let (proof, _blinding) = prove_range(value, 32, b"context").unwrap();
        assert!(verify_range(&proof, b"context").is_ok());
    }

    #[test]
    fn test_range_proof_out_of_range() {
        let result = prove_range(256, 8, b"test");
        assert!(result.is_err(), "Value 256 should not fit in 8 bits");
    }

    #[test]
    fn test_range_proof_wrong_context() {
        let (proof, _) = prove_range(42, 8, b"context A").unwrap();
        let result = verify_range(&proof, b"context B");
        assert!(result.is_err(), "Wrong context must fail verification");
    }

    #[test]
    fn test_range_proof_large_value() {
        // Test with a value that uses many bits (like a Solana lamport amount)
        let value = 1_000_000_000u64; // 1 SOL in lamports
        let (proof, _) = prove_range(value, 64, b"solana transfer").unwrap();
        assert!(verify_range(&proof, b"solana transfer").is_ok());
    }

    #[test]
    fn test_range_proof_tampered_bit_proof() {
        let (mut proof, _) = prove_range(42, 8, b"test").unwrap();

        // Tamper with a bit proof's commitment
        if let Some(bp) = proof.bit_proofs.get_mut(0) {
            let mut bytes = hex::decode(&bp.e0).unwrap();
            bytes[0] ^= 0xFF;
            bp.e0 = hex::encode(&bytes);
        }

        let result = verify_range(&proof, b"test");
        assert!(result.is_err(), "Tampered bit proof must fail");
    }

    #[test]
    fn test_range_proof_64bit() {
        // Full 64-bit range proof
        let value = u64::MAX - 1;
        let (proof, _) = prove_range(value, 64, b"max").unwrap();
        assert!(verify_range(&proof, b"max").is_ok());
        assert_eq!(proof.bit_proofs.len(), 64);
    }
}
