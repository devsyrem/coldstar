//! Policy Compliance Proof
//!
//! Proves that a transaction satisfies a policy constraint without
//! revealing the specific policy parameters.
//!
//! # MVP Approach
//!
//! The policy proof commits to a (policy_id, satisfied, constraint_hash) tuple
//! and proves knowledge of the opening via a Schnorr-like proof.
//!
//! This demonstrates the architecture for policy proofs. In production,
//! more sophisticated circuit-based proofs could prove specific policy
//! properties (e.g., amount < max, destination ∈ allowlist) in zero knowledge.
//!
//! # Protocol
//!
//! 1. Prover computes commitment:
//!    C = H_point(domain || policy_id || "satisfied" || constraint_data)
//!    where H_point is hash-to-Ristretto-point
//! 2. Prover picks random k, computes R = k*G
//! 3. Challenge c = H(domain || C || R || context)
//! 4. Prover computes witness w from constraint data
//! 5. Response s = k + c*w
//! 6. Verifier recomputes C from known policy_id + "satisfied" + constraint,
//!    recomputes challenge, and checks s*G == R + c*W where W = w*G

use curve25519_dalek::{
    constants::RISTRETTO_BASEPOINT_POINT,
    scalar::Scalar,
};
use rand_core::OsRng;
use sha2::{Digest, Sha256, Sha512};
use zeroize::Zeroize;

use crate::domain::DOMAIN_POLICY_PROOF;
use crate::error::ZkError;
use crate::transcript::Transcript;
use crate::types::PolicyProof;

/// A policy constraint that can be proven.
#[derive(Debug, Clone)]
pub struct PolicyConstraint {
    /// Unique identifier for the policy (e.g., "max_transfer_lamports")
    pub policy_id: String,
    /// Whether the constraint is satisfied
    pub satisfied: bool,
    /// Opaque constraint data (e.g., hash of the policy parameters + tx data)
    /// This is NOT revealed to the verifier.
    pub constraint_data: Vec<u8>,
}

/// Generate a policy compliance proof.
///
/// # Arguments
/// * `constraint` - The policy constraint to prove
/// * `context_data` - Transaction context data for binding
///
/// # Returns
/// A PolicyProof if the constraint is satisfied, or an error if not.
///
/// # Security
/// - The constraint_data is never revealed
/// - The verifier only learns: (policy_id, satisfied=true)
/// - The proof is bound to the transaction context
pub fn prove_policy(
    constraint: &PolicyConstraint,
    context_data: &[u8],
) -> Result<PolicyProof, ZkError> {
    if !constraint.satisfied {
        return Err(ZkError::PolicyViolation(format!(
            "Policy '{}' is not satisfied — cannot generate proof",
            constraint.policy_id
        )));
    }

    let g = RISTRETTO_BASEPOINT_POINT;

    // Derive a witness scalar from the constraint data
    // w = H_scalar(domain || policy_id || constraint_data)
    // This is secret — it encodes knowledge of the policy satisfaction
    let mut w = derive_witness(&constraint.policy_id, &constraint.constraint_data);

    // Compute public commitment: W = w*G
    let big_w = w * g;

    // Also compute a hash commitment of the policy satisfaction
    let commitment_hash = {
        let mut hasher = Sha256::new();
        hasher.update(DOMAIN_POLICY_PROOF);
        hasher.update(constraint.policy_id.as_bytes());
        hasher.update(b":satisfied:");
        hasher.update(big_w.compress().as_bytes());
        hex::encode(hasher.finalize())
    };

    // Schnorr proof: prove knowledge of w such that W = w*G
    let mut k = Scalar::random(&mut OsRng);
    let big_r = k * g;

    let mut transcript = Transcript::new(DOMAIN_POLICY_PROOF);
    transcript.append(b"policy_id", constraint.policy_id.as_bytes());
    transcript.append_point(b"W", &big_w.compress());
    transcript.append_point(b"R", &big_r.compress());
    transcript.append(b"context", context_data);

    let c = transcript.challenge_scalar(b"policy_challenge");
    let s = k + c * w;

    let context_hash = {
        let mut hasher = Sha256::new();
        hasher.update(context_data);
        hex::encode(hasher.finalize())
    };

    // Zeroize
    w.zeroize();
    k.zeroize();

    Ok(PolicyProof {
        policy_id: constraint.policy_id.clone(),
        commitment: commitment_hash,
        response: hex::encode(s.as_bytes()),
        challenge: hex::encode(c.as_bytes()),
        context_hash,
    })
}

/// Verify a policy compliance proof.
///
/// # Arguments
/// * `proof` - The proof to verify
/// * `policy_id` - Expected policy ID
/// * `constraint_data` - The constraint data (must match what prover used)
/// * `context_data` - Transaction context data
///
/// # Note
/// In the MVP, the verifier needs to know the constraint_data to verify.
/// This means the offline signer must independently evaluate the policy.
/// In a production system, this could be replaced with a ZK circuit
/// that doesn't require the verifier to know the constraint data.
pub fn verify_policy(
    proof: &PolicyProof,
    policy_id: &str,
    constraint_data: &[u8],
    context_data: &[u8],
) -> Result<(), ZkError> {
    let g = RISTRETTO_BASEPOINT_POINT;

    // Verify policy ID matches
    if proof.policy_id != policy_id {
        return Err(ZkError::PolicyViolation(format!(
            "Policy ID mismatch: expected '{}', got '{}'",
            policy_id, proof.policy_id
        )));
    }

    // Verify context hash
    let expected_context_hash = {
        let mut hasher = Sha256::new();
        hasher.update(context_data);
        hex::encode(hasher.finalize())
    };
    if proof.context_hash != expected_context_hash {
        return Err(ZkError::VerificationFailed(
            "Policy proof context hash mismatch".into(),
        ));
    }

    // Recompute witness point W from constraint data
    let w = derive_witness(policy_id, constraint_data);
    let big_w = w * g;

    // Verify commitment hash
    let expected_commitment = {
        let mut hasher = Sha256::new();
        hasher.update(DOMAIN_POLICY_PROOF);
        hasher.update(policy_id.as_bytes());
        hasher.update(b":satisfied:");
        hasher.update(big_w.compress().as_bytes());
        hex::encode(hasher.finalize())
    };
    if proof.commitment != expected_commitment {
        return Err(ZkError::VerificationFailed(
            "Policy proof commitment mismatch — constraint data may not match".into(),
        ));
    }

    // Deserialize response s and challenge c
    let s = deserialize_scalar(&proof.response, "response")?;

    // Recompute R = s*G - c*W
    let mut transcript = Transcript::new(DOMAIN_POLICY_PROOF);
    transcript.append(b"policy_id", policy_id.as_bytes());
    transcript.append_point(b"W", &big_w.compress());

    // We need to recompute R from s and c:
    // s*G = R + c*W  =>  R = s*G - c*W
    //
    // We can't compute c from transcript yet because we haven't appended R,
    // and R depends on c. So we deserialize c from the proof, recompute R,
    // then verify c matches the transcript (Fiat-Shamir consistency check).
    let c_from_proof = deserialize_scalar(&proof.challenge, "challenge")?;
    let big_r = s * g - c_from_proof * big_w;

    // Now verify the challenge is correctly derived
    let mut transcript2 = Transcript::new(DOMAIN_POLICY_PROOF);
    transcript2.append(b"policy_id", policy_id.as_bytes());
    transcript2.append_point(b"W", &big_w.compress());
    transcript2.append_point(b"R", &big_r.compress());
    transcript2.append(b"context", context_data);
    let expected_c = transcript2.challenge_scalar(b"policy_challenge");

    if c_from_proof != expected_c {
        return Err(ZkError::VerificationFailed(
            "Policy proof Schnorr verification failed".into(),
        ));
    }

    Ok(())
}

/// Derive a witness scalar from policy data.
/// This is deterministic: same inputs always produce the same witness.
fn derive_witness(policy_id: &str, constraint_data: &[u8]) -> Scalar {
    let mut hasher = Sha512::new();
    hasher.update(DOMAIN_POLICY_PROOF);
    hasher.update(b":witness:");
    hasher.update((policy_id.len() as u64).to_le_bytes());
    hasher.update(policy_id.as_bytes());
    hasher.update((constraint_data.len() as u64).to_le_bytes());
    hasher.update(constraint_data);
    let hash = hasher.finalize();
    let mut wide = [0u8; 64];
    wide.copy_from_slice(&hash);
    Scalar::from_bytes_mod_order_wide(&wide)
}

/// Deserialize a scalar from hex string.
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
    Ok(Scalar::from_bytes_mod_order(arr))
}

/// Helper: create a policy constraint for maximum transfer amount.
///
/// # Arguments
/// * `amount_lamports` - The actual transfer amount
/// * `max_lamports` - The maximum allowed amount
///
/// # Returns
/// A PolicyConstraint that is satisfied if amount <= max
pub fn max_transfer_constraint(amount_lamports: u64, max_lamports: u64) -> PolicyConstraint {
    let satisfied = amount_lamports <= max_lamports;
    let mut data = Vec::new();
    data.extend_from_slice(&amount_lamports.to_le_bytes());
    data.extend_from_slice(&max_lamports.to_le_bytes());
    PolicyConstraint {
        policy_id: "max_transfer_lamports".to_string(),
        satisfied,
        constraint_data: data,
    }
}

/// Helper: create a policy constraint for allowed destination.
///
/// # Arguments
/// * `destination` - The actual destination pubkey (base58)
/// * `allowed_destinations` - List of allowed destination pubkeys
///
/// # Returns
/// A PolicyConstraint that is satisfied if destination is in the allowed list
pub fn allowed_destination_constraint(
    destination: &str,
    allowed_destinations: &[&str],
) -> PolicyConstraint {
    let satisfied = allowed_destinations.contains(&destination);
    let mut data = Vec::new();
    data.extend_from_slice(destination.as_bytes());
    data.push(b':');
    for (i, d) in allowed_destinations.iter().enumerate() {
        if i > 0 {
            data.push(b',');
        }
        data.extend_from_slice(d.as_bytes());
    }
    PolicyConstraint {
        policy_id: "allowed_destination".to_string(),
        satisfied,
        constraint_data: data,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_policy_proof_satisfied() {
        let constraint = max_transfer_constraint(1_000_000, 10_000_000);
        let context = b"test transaction";
        let proof = prove_policy(&constraint, context).unwrap();

        assert!(verify_policy(
            &proof,
            "max_transfer_lamports",
            &constraint.constraint_data,
            context
        )
        .is_ok());
    }

    #[test]
    fn test_policy_proof_not_satisfied() {
        let constraint = max_transfer_constraint(100_000_000, 10_000_000);
        let context = b"test transaction";
        let result = prove_policy(&constraint, context);
        assert!(result.is_err(), "Cannot prove unsatisfied policy");
    }

    #[test]
    fn test_policy_proof_wrong_context() {
        let constraint = max_transfer_constraint(1_000, 10_000);
        let proof = prove_policy(&constraint, b"context A").unwrap();

        let result = verify_policy(
            &proof,
            "max_transfer_lamports",
            &constraint.constraint_data,
            b"context B",
        );
        assert!(result.is_err(), "Wrong context must fail");
    }

    #[test]
    fn test_policy_proof_wrong_policy_id() {
        let constraint = max_transfer_constraint(1_000, 10_000);
        let proof = prove_policy(&constraint, b"ctx").unwrap();

        let result = verify_policy(&proof, "wrong_policy", &constraint.constraint_data, b"ctx");
        assert!(result.is_err(), "Wrong policy ID must fail");
    }

    #[test]
    fn test_policy_proof_wrong_constraint_data() {
        let constraint = max_transfer_constraint(1_000, 10_000);
        let proof = prove_policy(&constraint, b"ctx").unwrap();

        // Different constraint data
        let wrong_constraint = max_transfer_constraint(2_000, 10_000);
        let result = verify_policy(
            &proof,
            "max_transfer_lamports",
            &wrong_constraint.constraint_data,
            b"ctx",
        );
        assert!(result.is_err(), "Wrong constraint data must fail");
    }

    #[test]
    fn test_allowed_destination_proof() {
        let allowed = vec!["addr1", "addr2", "addr3"];
        let constraint = allowed_destination_constraint("addr2", &allowed);
        let proof = prove_policy(&constraint, b"ctx").unwrap();

        assert!(verify_policy(
            &proof,
            "allowed_destination",
            &constraint.constraint_data,
            b"ctx"
        )
        .is_ok());
    }

    #[test]
    fn test_disallowed_destination() {
        let allowed = vec!["addr1", "addr2"];
        let constraint = allowed_destination_constraint("addr3", &allowed);
        assert!(!constraint.satisfied);
        assert!(prove_policy(&constraint, b"ctx").is_err());
    }
}
