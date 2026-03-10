//! Fiat-Shamir transcript for non-interactive proofs.
//!
//! This module provides a domain-separated hash-based transcript
//! that converts interactive Sigma protocols into non-interactive
//! proofs via the Fiat-Shamir heuristic.
//!
//! # Security Properties
//! - Domain separation: each transcript starts with a unique domain tag
//! - Sequential binding: each append operation includes all prior state
//! - Deterministic challenges: challenges are derived from the full transcript

use curve25519_dalek::scalar::Scalar;
use sha2::{Digest, Sha512};

/// A Fiat-Shamir transcript for generating non-interactive proof challenges.
///
/// Uses SHA-512 internally and produces 64-byte digests that are
/// reduced to Scalars via `Scalar::from_bytes_mod_order_wide`.
pub struct Transcript {
    hasher: Sha512,
}

impl Transcript {
    /// Create a new transcript with a domain separation tag.
    ///
    /// # Arguments
    /// * `domain` - Domain tag bytes (e.g., `DOMAIN_OWNERSHIP_PROOF`)
    pub fn new(domain: &[u8]) -> Self {
        let mut hasher = Sha512::new();
        // Include domain tag length to prevent ambiguity
        hasher.update((domain.len() as u64).to_le_bytes());
        hasher.update(domain);
        Transcript { hasher }
    }

    /// Append a labeled byte slice to the transcript.
    ///
    /// # Arguments
    /// * `label` - A human-readable label for this data item
    /// * `data` - The data bytes to append
    pub fn append(&mut self, label: &[u8], data: &[u8]) {
        // Include label + data with length prefixes to prevent ambiguity
        self.hasher.update((label.len() as u64).to_le_bytes());
        self.hasher.update(label);
        self.hasher.update((data.len() as u64).to_le_bytes());
        self.hasher.update(data);
    }

    /// Append a compressed Ristretto point to the transcript.
    pub fn append_point(&mut self, label: &[u8], point: &curve25519_dalek::ristretto::CompressedRistretto) {
        self.append(label, point.as_bytes());
    }

    /// Append a scalar to the transcript.
    pub fn append_scalar(&mut self, label: &[u8], scalar: &Scalar) {
        self.append(label, scalar.as_bytes());
    }

    /// Extract a challenge scalar from the transcript.
    ///
    /// This finalizes the current hash state and produces a scalar.
    /// After calling this, the transcript can still be used (SHA-512
    /// clone is taken internally).
    ///
    /// # Returns
    /// A scalar derived from the transcript state via
    /// `Scalar::from_bytes_mod_order_wide` on the SHA-512 digest.
    pub fn challenge_scalar(&self, label: &[u8]) -> Scalar {
        let mut hasher = self.hasher.clone();
        hasher.update(b"challenge");
        hasher.update((label.len() as u64).to_le_bytes());
        hasher.update(label);
        let hash = hasher.finalize();
        let mut wide = [0u8; 64];
        wide.copy_from_slice(&hash);
        Scalar::from_bytes_mod_order_wide(&wide)
    }

    /// Get the current transcript hash as raw bytes (for context hashing).
    pub fn digest(&self) -> [u8; 64] {
        let hasher = self.hasher.clone();
        let hash = hasher.finalize();
        let mut out = [0u8; 64];
        out.copy_from_slice(&hash);
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transcript_determinism() {
        let mut t1 = Transcript::new(b"test.domain");
        t1.append(b"data", b"hello");
        let c1 = t1.challenge_scalar(b"ch");

        let mut t2 = Transcript::new(b"test.domain");
        t2.append(b"data", b"hello");
        let c2 = t2.challenge_scalar(b"ch");

        assert_eq!(c1, c2, "Same inputs must produce same challenge");
    }

    #[test]
    fn test_transcript_domain_separation() {
        let mut t1 = Transcript::new(b"domain.A");
        t1.append(b"data", b"hello");
        let c1 = t1.challenge_scalar(b"ch");

        let mut t2 = Transcript::new(b"domain.B");
        t2.append(b"data", b"hello");
        let c2 = t2.challenge_scalar(b"ch");

        assert_ne!(c1, c2, "Different domains must produce different challenges");
    }

    #[test]
    fn test_transcript_ordering_matters() {
        let mut t1 = Transcript::new(b"test");
        t1.append(b"a", b"1");
        t1.append(b"b", b"2");
        let c1 = t1.challenge_scalar(b"ch");

        let mut t2 = Transcript::new(b"test");
        t2.append(b"b", b"2");
        t2.append(b"a", b"1");
        let c2 = t2.challenge_scalar(b"ch");

        assert_ne!(c1, c2, "Different ordering must produce different challenges");
    }
}
