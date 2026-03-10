//! Pedersen commitment scheme on the Ristretto group.
//!
//! A Pedersen commitment to value `v` with blinding factor `r` is:
//!   C = v*G + r*H
//!
//! where G is the standard Ristretto basepoint and H is a secondary
//! generator derived via hash-to-point (nothing-up-my-sleeve construction).
//!
//! # Properties
//! - **Hiding**: Given C, an adversary cannot determine v (information-theoretic)
//! - **Binding**: Given C, no efficient adversary can find (v', r') ≠ (v, r)
//!   such that v'*G + r'*H = C (computational, assuming DLP hardness)
//! - **Homomorphic**: C(v1, r1) + C(v2, r2) = C(v1+v2, r1+r2)

use curve25519_dalek::{
    constants::RISTRETTO_BASEPOINT_POINT,
    ristretto::{CompressedRistretto, RistrettoPoint},
    scalar::Scalar,
};
use sha2::Sha512;

use crate::domain::DOMAIN_GENERATOR_H;

/// Get the secondary generator H for Pedersen commitments.
///
/// H is derived from G using hash-to-point with a fixed domain tag.
/// This is a nothing-up-my-sleeve construction: nobody knows the
/// discrete log of H with respect to G.
///
/// SECURITY: This function MUST always return the same point.
/// Changing the domain tag would break all existing commitments.
pub fn generator_h() -> RistrettoPoint {
    RistrettoPoint::hash_from_bytes::<Sha512>(DOMAIN_GENERATOR_H)
}

/// The standard basepoint G (Ristretto).
pub fn generator_g() -> RistrettoPoint {
    RISTRETTO_BASEPOINT_POINT
}

/// Create a Pedersen commitment: C = v*G + r*H
///
/// # Arguments
/// * `value` - The value to commit to (as a Scalar)
/// * `blinding` - The blinding factor (as a Scalar)
///
/// # Returns
/// The commitment point C
pub fn commit(value: &Scalar, blinding: &Scalar) -> RistrettoPoint {
    let g = generator_g();
    let h = generator_h();
    value * g + blinding * h
}

/// Create a Pedersen commitment to a u64 value.
///
/// # Arguments
/// * `value` - The u64 value to commit to
/// * `blinding` - The blinding factor
///
/// # Returns
/// The commitment point C
pub fn commit_u64(value: u64, blinding: &Scalar) -> RistrettoPoint {
    let v = Scalar::from(value);
    commit(&v, blinding)
}

/// Verify that a commitment opens to the claimed value and blinding factor.
///
/// # Arguments
/// * `commitment` - The commitment point C
/// * `value` - The claimed value
/// * `blinding` - The claimed blinding factor
///
/// # Returns
/// true if C == value*G + blinding*H
pub fn verify_opening(commitment: &RistrettoPoint, value: &Scalar, blinding: &Scalar) -> bool {
    let expected = commit(value, blinding);
    commitment == &expected
}

/// Serialize a commitment point to hex string.
pub fn commitment_to_hex(point: &RistrettoPoint) -> String {
    hex::encode(point.compress().as_bytes())
}

/// Deserialize a commitment point from hex string.
pub fn commitment_from_hex(hex_str: &str) -> Result<RistrettoPoint, crate::error::ZkError> {
    let bytes = hex::decode(hex_str)?;
    if bytes.len() != 32 {
        return Err(crate::error::ZkError::InvalidCommitment(
            format!("Expected 32 bytes, got {}", bytes.len()),
        ));
    }
    let mut arr = [0u8; 32];
    arr.copy_from_slice(&bytes);
    CompressedRistretto(arr)
        .decompress()
        .ok_or_else(|| crate::error::ZkError::InvalidCommitment("Point decompression failed".into()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand_core::OsRng;

    #[test]
    fn test_commitment_hiding() {
        // Same value, different blinding → different commitments
        let v = Scalar::from(42u64);
        let r1 = Scalar::random(&mut OsRng);
        let r2 = Scalar::random(&mut OsRng);
        let c1 = commit(&v, &r1);
        let c2 = commit(&v, &r2);
        assert_ne!(c1, c2, "Different blinding factors must produce different commitments");
    }

    #[test]
    fn test_commitment_binding() {
        // Same commitment, verify opening
        let v = Scalar::from(100u64);
        let r = Scalar::random(&mut OsRng);
        let c = commit(&v, &r);
        assert!(verify_opening(&c, &v, &r), "Commitment must verify with correct opening");

        // Wrong value must fail
        let v_wrong = Scalar::from(101u64);
        assert!(!verify_opening(&c, &v_wrong, &r), "Commitment must not verify with wrong value");
    }

    #[test]
    fn test_commitment_homomorphic() {
        let v1 = Scalar::from(30u64);
        let r1 = Scalar::random(&mut OsRng);
        let c1 = commit(&v1, &r1);

        let v2 = Scalar::from(12u64);
        let r2 = Scalar::random(&mut OsRng);
        let c2 = commit(&v2, &r2);

        let v_sum = v1 + v2;
        let r_sum = r1 + r2;
        let c_sum = commit(&v_sum, &r_sum);

        assert_eq!(c1 + c2, c_sum, "Pedersen commitments must be additively homomorphic");
    }

    #[test]
    fn test_commitment_serialization_roundtrip() {
        let v = Scalar::from(999u64);
        let r = Scalar::random(&mut OsRng);
        let c = commit(&v, &r);

        let hex_str = commitment_to_hex(&c);
        let c2 = commitment_from_hex(&hex_str).unwrap();
        assert_eq!(c, c2, "Commitment must survive serialization roundtrip");
    }

    #[test]
    fn test_generator_h_is_not_g() {
        let g = generator_g();
        let h = generator_h();
        assert_ne!(g, h, "G and H must be different points");
    }

    #[test]
    fn test_generator_h_deterministic() {
        let h1 = generator_h();
        let h2 = generator_h();
        assert_eq!(h1, h2, "Generator H must be deterministic");
    }
}
