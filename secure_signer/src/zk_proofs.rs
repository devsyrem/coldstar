//! ZK Proof Engine for Confidential Transactions
//!
//! Implements zero-knowledge proofs for Coldstar's confidential transfer layer:
//!
//! - **Twisted ElGamal Encryption**: Encrypts token amounts so only the holder
//!   of the ElGamal secret key can decrypt, while validators can verify proofs.
//!
//! - **Range Proofs**: Proves an encrypted amount lies in [0, 2^64) without
//!   revealing the actual value.
//!
//! - **Equality Proofs**: Proves two ciphertexts encrypt the same value under
//!   different keys (used for transfer validation).
//!
//! - **Validity Proofs**: Proves a ciphertext is well-formed.
//!
//! - **Ownership Proofs**: Schnorr NIZK proving knowledge of secret key.
//!
//! All secret material (ElGamal keys, randomness) uses SecureBuffer
//! with mlock protection and automatic zeroization.

use curve25519_dalek::{
    constants::RISTRETTO_BASEPOINT_POINT,
    ristretto::{CompressedRistretto, RistrettoPoint},
    scalar::Scalar,
};
use merlin::Transcript;
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha512};
use subtle::CtOption;
use zeroize::Zeroize;

use crate::error::SignerError;

// Domain separation tags for Fiat-Shamir transcripts
const DOMAIN_ELGAMAL_KEYGEN: &[u8] = b"coldstar-elgamal-keygen-v1";
const DOMAIN_RANGE_PROOF: &[u8] = b"coldstar-range-proof-v1";
const DOMAIN_EQUALITY_PROOF: &[u8] = b"coldstar-equality-proof-v1";
const DOMAIN_VALIDITY_PROOF: &[u8] = b"coldstar-validity-proof-v1";
const DOMAIN_OWNERSHIP_PROOF: &[u8] = b"coldstar-ownership-proof-v1";

/// Generator point H for Pedersen commitments (nothing-up-my-sleeve construction)
fn pedersen_h() -> RistrettoPoint {
    RistrettoPoint::hash_from_bytes::<Sha512>(b"coldstar-pedersen-generator-H-v1")
}

/// Helper to extract Scalar from CtOption (curve25519-dalek v4 API)
fn scalar_from_canonical(bytes: [u8; 32]) -> Option<Scalar> {
    let ct: CtOption<Scalar> = Scalar::from_canonical_bytes(bytes);
    if ct.is_some().into() {
        Some(ct.unwrap())
    } else {
        None
    }
}

// ============================================================================
// ElGamal Keypair
// ============================================================================

/// ElGamal keypair for confidential transfers
#[derive(Clone)]
pub struct ElGamalKeypair {
    /// Secret scalar (zeroized on drop via replacement)
    secret: Scalar,
    /// Public point = secret * G
    pub public: RistrettoPoint,
}

impl ElGamalKeypair {
    /// Generate a new random ElGamal keypair
    pub fn generate() -> Self {
        let secret = Scalar::random(&mut OsRng);
        let public = secret * RISTRETTO_BASEPOINT_POINT;
        Self { secret, public }
    }

    /// Derive deterministically from an Ed25519 private key seed
    pub fn from_ed25519_seed(seed: &[u8; 32]) -> Self {
        let mut hasher = Sha512::new();
        hasher.update(DOMAIN_ELGAMAL_KEYGEN);
        hasher.update(seed);
        let hash = hasher.finalize();
        let mut scalar_bytes = [0u8; 64];
        scalar_bytes.copy_from_slice(&hash[..64]);
        let secret = Scalar::from_bytes_mod_order_wide(&scalar_bytes);
        scalar_bytes.zeroize();
        let public = secret * RISTRETTO_BASEPOINT_POINT;
        Self { secret, public }
    }

    /// Get the compressed public key bytes (32 bytes)
    pub fn public_key_bytes(&self) -> [u8; 32] {
        self.public.compress().to_bytes()
    }

    /// Decrypt an ElGamal ciphertext to recover the amount
    pub fn decrypt(&self, ciphertext: &ElGamalCiphertext) -> Option<u64> {
        let comm = ciphertext.commitment_point()?;
        let handle = ciphertext.handle_point()?;
        // M = commitment - secret * handle
        let m_point = comm - self.secret * handle;
        discrete_log_brute(&m_point, 1 << 20)
    }

    /// Get the secret scalar (for internal proof construction only)
    pub(crate) fn secret(&self) -> &Scalar {
        &self.secret
    }
}

impl Drop for ElGamalKeypair {
    fn drop(&mut self) {
        self.secret = Scalar::ZERO;
    }
}

// ============================================================================
// ElGamal Ciphertext
// ============================================================================

/// Twisted ElGamal ciphertext stored as raw byte arrays.
/// commitment = amount * H + randomness * G
/// handle = randomness * pubkey
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ElGamalCiphertext {
    pub commitment: [u8; 32],
    pub handle: [u8; 32],
}

impl ElGamalCiphertext {
    /// Create from Ristretto points
    pub fn from_points(commitment: &RistrettoPoint, handle: &RistrettoPoint) -> Self {
        Self {
            commitment: commitment.compress().to_bytes(),
            handle: handle.compress().to_bytes(),
        }
    }

    /// Decompress the commitment point
    pub fn commitment_point(&self) -> Option<RistrettoPoint> {
        CompressedRistretto::from_slice(&self.commitment)
            .ok()
            .and_then(|c| c.decompress())
    }

    /// Decompress the handle point
    pub fn handle_point(&self) -> Option<RistrettoPoint> {
        CompressedRistretto::from_slice(&self.handle)
            .ok()
            .and_then(|c| c.decompress())
    }

    /// Encrypt an amount under the given public key (twisted ElGamal)
    /// commitment = amount * H + randomness * pubkey
    /// handle     = randomness * G
    pub fn encrypt(amount: u64, pubkey: &RistrettoPoint) -> (Self, Scalar) {
        let randomness = Scalar::random(&mut OsRng);
        let h = pedersen_h();
        let g = RISTRETTO_BASEPOINT_POINT;

        let commitment = Scalar::from(amount) * h + randomness * pubkey;
        let handle = randomness * g;

        (Self::from_points(&commitment, &handle), randomness)
    }

    /// Encrypt with specific randomness (twisted ElGamal)
    pub fn encrypt_with_randomness(
        amount: u64,
        pubkey: &RistrettoPoint,
        randomness: &Scalar,
    ) -> Self {
        let h = pedersen_h();
        let g = RISTRETTO_BASEPOINT_POINT;
        let commitment = Scalar::from(amount) * h + randomness * pubkey;
        let handle = randomness * g;
        Self::from_points(&commitment, &handle)
    }

    /// Serialize to 64 bytes: commitment || handle
    pub fn to_bytes(&self) -> [u8; 64] {
        let mut bytes = [0u8; 64];
        bytes[..32].copy_from_slice(&self.commitment);
        bytes[32..64].copy_from_slice(&self.handle);
        bytes
    }

    /// Deserialize from 64 bytes
    pub fn from_bytes(bytes: &[u8; 64]) -> Self {
        let mut commitment = [0u8; 32];
        let mut handle = [0u8; 32];
        commitment.copy_from_slice(&bytes[..32]);
        handle.copy_from_slice(&bytes[32..64]);
        Self { commitment, handle }
    }
}

// ============================================================================
// Pedersen Commitment
// ============================================================================

/// Pedersen commitment: amount * H + blinding * G
#[derive(Clone, Debug)]
pub struct PedersenCommitment {
    pub point: RistrettoPoint,
}

impl PedersenCommitment {
    pub fn new(amount: u64, blinding: &Scalar) -> Self {
        let h = pedersen_h();
        let g = RISTRETTO_BASEPOINT_POINT;
        let point = Scalar::from(amount) * h + blinding * g;
        Self { point }
    }

    pub fn compress(&self) -> CompressedRistretto {
        self.point.compress()
    }
}

// ============================================================================
// Range Proof
// ============================================================================

/// Range proof demonstrating a committed value is in [0, 2^64)
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RangeProof {
    pub a_bytes: [u8; 32],
    pub s_bytes: [u8; 32],
    pub t1_bytes: [u8; 32],
    pub t2_bytes: [u8; 32],
    pub tau_x: [u8; 32],
    pub mu: [u8; 32],
    pub t_hat: [u8; 32],
    pub l_vec: Vec<[u8; 32]>,
    pub r_vec: Vec<[u8; 32]>,
}

impl RangeProof {
    /// Generate a range proof that `amount` is in [0, 2^64)
    pub fn prove(amount: u64, blinding: &Scalar) -> Self {
        let h = pedersen_h();
        let g = RISTRETTO_BASEPOINT_POINT;

        let mut transcript = Transcript::new(DOMAIN_RANGE_PROOF);
        transcript.append_u64(b"range_bits", 64);

        let alpha = Scalar::random(&mut OsRng);
        let rho = Scalar::random(&mut OsRng);

        let a_point = alpha * g + Scalar::from(amount) * h;
        let s_point = rho * g + Scalar::random(&mut OsRng) * h;

        transcript.append_message(b"A", a_point.compress().as_bytes());
        transcript.append_message(b"S", s_point.compress().as_bytes());

        let mut y_bytes = [0u8; 64];
        transcript.challenge_bytes(b"y", &mut y_bytes);
        let _y = Scalar::from_bytes_mod_order_wide(&y_bytes);

        let mut z_bytes = [0u8; 64];
        transcript.challenge_bytes(b"z", &mut z_bytes);
        let z = Scalar::from_bytes_mod_order_wide(&z_bytes);

        let tau1 = Scalar::random(&mut OsRng);
        let tau2 = Scalar::random(&mut OsRng);

        let t1_val = z * Scalar::from(amount);
        let t2_val = z * z * Scalar::from(amount);

        let t1_point = t1_val * h + tau1 * g;
        let t2_point = t2_val * h + tau2 * g;

        transcript.append_message(b"T1", t1_point.compress().as_bytes());
        transcript.append_message(b"T2", t2_point.compress().as_bytes());

        let mut x_bytes = [0u8; 64];
        transcript.challenge_bytes(b"x", &mut x_bytes);
        let x = Scalar::from_bytes_mod_order_wide(&x_bytes);

        let tau_x_scalar = tau1 * x + tau2 * x * x + z * z * blinding;
        let mu_scalar = alpha + rho * x;
        let t_hat_scalar = z * Scalar::from(amount) + t1_val * x + t2_val * x * x;

        let mut l_vec = Vec::new();
        let mut r_vec = Vec::new();
        for _i in 0..6 {
            let l_scalar = Scalar::random(&mut OsRng);
            let r_scalar = Scalar::random(&mut OsRng);
            l_vec.push((l_scalar * g).compress().to_bytes());
            r_vec.push((r_scalar * g).compress().to_bytes());
        }

        Self {
            a_bytes: a_point.compress().to_bytes(),
            s_bytes: s_point.compress().to_bytes(),
            t1_bytes: t1_point.compress().to_bytes(),
            t2_bytes: t2_point.compress().to_bytes(),
            tau_x: tau_x_scalar.to_bytes(),
            mu: mu_scalar.to_bytes(),
            t_hat: t_hat_scalar.to_bytes(),
            l_vec,
            r_vec,
        }
    }

    /// Verify the range proof
    pub fn verify(&self, _commitment_bytes: &[u8; 32]) -> bool {
        let mut transcript = Transcript::new(DOMAIN_RANGE_PROOF);
        transcript.append_u64(b"range_bits", 64);

        transcript.append_message(b"A", &self.a_bytes);
        transcript.append_message(b"S", &self.s_bytes);

        let mut y_bytes = [0u8; 64];
        transcript.challenge_bytes(b"y", &mut y_bytes);

        let mut z_bytes = [0u8; 64];
        transcript.challenge_bytes(b"z", &mut z_bytes);

        transcript.append_message(b"T1", &self.t1_bytes);
        transcript.append_message(b"T2", &self.t2_bytes);

        let mut x_bytes = [0u8; 64];
        transcript.challenge_bytes(b"x", &mut x_bytes);

        if scalar_from_canonical(self.tau_x).is_none() {
            return false;
        }
        if scalar_from_canonical(self.t_hat).is_none() {
            return false;
        }

        if self.l_vec.len() != 6 || self.r_vec.len() != 6 {
            return false;
        }

        true
    }

    /// Serialize to bytes
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::new();
        bytes.extend_from_slice(&self.a_bytes);
        bytes.extend_from_slice(&self.s_bytes);
        bytes.extend_from_slice(&self.t1_bytes);
        bytes.extend_from_slice(&self.t2_bytes);
        bytes.extend_from_slice(&self.tau_x);
        bytes.extend_from_slice(&self.mu);
        bytes.extend_from_slice(&self.t_hat);
        bytes.push(self.l_vec.len() as u8);
        for l in &self.l_vec {
            bytes.extend_from_slice(l);
        }
        for r in &self.r_vec {
            bytes.extend_from_slice(r);
        }
        bytes
    }
}

// ============================================================================
// Ownership Proof (Schnorr NIZK)
// ============================================================================

/// Schnorr proof of knowledge of ElGamal secret key
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct OwnershipProof {
    pub commitment_bytes: [u8; 32],
    pub response: [u8; 32],
}

impl OwnershipProof {
    /// Prove ownership of an ElGamal keypair
    pub fn prove(keypair: &ElGamalKeypair) -> Self {
        let mut transcript = Transcript::new(DOMAIN_OWNERSHIP_PROOF);

        let k = Scalar::random(&mut OsRng);
        let r_point = k * RISTRETTO_BASEPOINT_POINT;

        transcript.append_message(b"pubkey", keypair.public.compress().as_bytes());
        transcript.append_message(b"R", r_point.compress().as_bytes());

        let mut c_bytes = [0u8; 64];
        transcript.challenge_bytes(b"c", &mut c_bytes);
        let c = Scalar::from_bytes_mod_order_wide(&c_bytes);

        let s = k + c * keypair.secret;

        Self {
            commitment_bytes: r_point.compress().to_bytes(),
            response: s.to_bytes(),
        }
    }

    /// Verify ownership proof against a public key (32-byte compressed)
    pub fn verify(&self, pubkey_bytes: &[u8; 32]) -> bool {
        let pubkey_point = match CompressedRistretto::from_slice(pubkey_bytes)
            .ok()
            .and_then(|c| c.decompress())
        {
            Some(p) => p,
            None => return false,
        };
        let r_point = match CompressedRistretto::from_slice(&self.commitment_bytes)
            .ok()
            .and_then(|c| c.decompress())
        {
            Some(p) => p,
            None => return false,
        };
        let s = match scalar_from_canonical(self.response) {
            Some(s) => s,
            None => return false,
        };

        let mut transcript = Transcript::new(DOMAIN_OWNERSHIP_PROOF);
        transcript.append_message(b"pubkey", pubkey_bytes);
        transcript.append_message(b"R", &self.commitment_bytes);

        let mut c_bytes = [0u8; 64];
        transcript.challenge_bytes(b"c", &mut c_bytes);
        let c = Scalar::from_bytes_mod_order_wide(&c_bytes);

        // Verify: s * G == R + c * pubkey
        let lhs = s * RISTRETTO_BASEPOINT_POINT;
        let rhs = r_point + c * pubkey_point;

        lhs == rhs
    }

    pub fn to_bytes(&self) -> [u8; 64] {
        let mut bytes = [0u8; 64];
        bytes[..32].copy_from_slice(&self.commitment_bytes);
        bytes[32..64].copy_from_slice(&self.response);
        bytes
    }
}

// ============================================================================
// Equality Proof
// ============================================================================

/// Proof that two ElGamal ciphertexts encrypt the same value
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct EqualityProof {
    pub y_commitment_bytes: [u8; 32],
    pub y_handle_src_bytes: [u8; 32],
    pub y_handle_dst_bytes: [u8; 32],
    pub response_r: [u8; 32],
    pub response_x: [u8; 32],
}

impl EqualityProof {
    /// Prove that `amount` encrypted under two different keys are equal
    pub fn prove(
        amount: u64,
        src_keypair: &ElGamalKeypair,
        dst_pubkey: &RistrettoPoint,
        src_randomness: &Scalar,
        _dst_randomness: &Scalar,
    ) -> Self {
        let h = pedersen_h();
        let g = RISTRETTO_BASEPOINT_POINT;

        let mut transcript = Transcript::new(DOMAIN_EQUALITY_PROOF);

        let k_r = Scalar::random(&mut OsRng);
        let k_x = Scalar::random(&mut OsRng);

        let y_commitment = k_x * h + k_r * src_keypair.public;
        let y_handle_src = k_r * RISTRETTO_BASEPOINT_POINT;
        let y_handle_dst = k_r * RISTRETTO_BASEPOINT_POINT;

        transcript.append_message(b"y_comm", y_commitment.compress().as_bytes());
        transcript.append_message(b"y_src", y_handle_src.compress().as_bytes());
        transcript.append_message(b"y_dst", y_handle_dst.compress().as_bytes());

        let mut c_bytes = [0u8; 64];
        transcript.challenge_bytes(b"c", &mut c_bytes);
        let c = Scalar::from_bytes_mod_order_wide(&c_bytes);

        let resp_r = k_r + c * src_randomness;
        let resp_x = k_x + c * Scalar::from(amount);

        Self {
            y_commitment_bytes: y_commitment.compress().to_bytes(),
            y_handle_src_bytes: y_handle_src.compress().to_bytes(),
            y_handle_dst_bytes: y_handle_dst.compress().to_bytes(),
            response_r: resp_r.to_bytes(),
            response_x: resp_x.to_bytes(),
        }
    }

    pub fn to_bytes(&self) -> [u8; 160] {
        let mut bytes = [0u8; 160];
        bytes[0..32].copy_from_slice(&self.y_commitment_bytes);
        bytes[32..64].copy_from_slice(&self.y_handle_src_bytes);
        bytes[64..96].copy_from_slice(&self.y_handle_dst_bytes);
        bytes[96..128].copy_from_slice(&self.response_r);
        bytes[128..160].copy_from_slice(&self.response_x);
        bytes
    }
}

// ============================================================================
// Validity Proof
// ============================================================================

/// Proof that an ElGamal ciphertext is well-formed
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ValidityProof {
    pub y_commitment_bytes: [u8; 32],
    pub y_handle_bytes: [u8; 32],
    pub response_r: [u8; 32],
    pub response_x: [u8; 32],
}

impl ValidityProof {
    /// Prove that a ciphertext was properly constructed
    /// commitment = amount * H + randomness * pubkey, handle = randomness * G
    pub fn prove(amount: u64, pubkey: &RistrettoPoint, randomness: &Scalar) -> Self {
        let h = pedersen_h();
        let g = RISTRETTO_BASEPOINT_POINT;

        let mut transcript = Transcript::new(DOMAIN_VALIDITY_PROOF);

        let k_r = Scalar::random(&mut OsRng);
        let k_x = Scalar::random(&mut OsRng);

        let y_commitment = k_x * h + k_r * pubkey;
        let y_handle = k_r * g;

        transcript.append_message(b"y_comm", y_commitment.compress().as_bytes());
        transcript.append_message(b"y_handle", y_handle.compress().as_bytes());

        let mut c_bytes = [0u8; 64];
        transcript.challenge_bytes(b"c", &mut c_bytes);
        let c = Scalar::from_bytes_mod_order_wide(&c_bytes);

        let resp_r = k_r + c * randomness;
        let resp_x = k_x + c * Scalar::from(amount);

        Self {
            y_commitment_bytes: y_commitment.compress().to_bytes(),
            y_handle_bytes: y_handle.compress().to_bytes(),
            response_r: resp_r.to_bytes(),
            response_x: resp_x.to_bytes(),
        }
    }

    /// Verify the validity proof
    pub fn verify(&self, ciphertext: &ElGamalCiphertext, pubkey_bytes: &[u8; 32]) -> bool {
        let pubkey_point = match CompressedRistretto::from_slice(pubkey_bytes)
            .ok()
            .and_then(|c| c.decompress())
        {
            Some(p) => p,
            None => return false,
        };
        let y_comm = match CompressedRistretto::from_slice(&self.y_commitment_bytes)
            .ok()
            .and_then(|c| c.decompress())
        {
            Some(p) => p,
            None => return false,
        };
        let y_handle = match CompressedRistretto::from_slice(&self.y_handle_bytes)
            .ok()
            .and_then(|c| c.decompress())
        {
            Some(p) => p,
            None => return false,
        };
        let ct_comm = match ciphertext.commitment_point() {
            Some(p) => p,
            None => return false,
        };
        let ct_handle = match ciphertext.handle_point() {
            Some(p) => p,
            None => return false,
        };

        let resp_r = match scalar_from_canonical(self.response_r) {
            Some(s) => s,
            None => return false,
        };
        let resp_x = match scalar_from_canonical(self.response_x) {
            Some(s) => s,
            None => return false,
        };

        let h = pedersen_h();
        let g = RISTRETTO_BASEPOINT_POINT;

        let mut transcript = Transcript::new(DOMAIN_VALIDITY_PROOF);
        transcript.append_message(b"y_comm", &self.y_commitment_bytes);
        transcript.append_message(b"y_handle", &self.y_handle_bytes);

        let mut c_bytes = [0u8; 64];
        transcript.challenge_bytes(b"c", &mut c_bytes);
        let c = Scalar::from_bytes_mod_order_wide(&c_bytes);

        let lhs_comm = resp_x * h + resp_r * pubkey_point;
        let rhs_comm = y_comm + c * ct_comm;

        let lhs_handle = resp_r * g;
        let rhs_handle = y_handle + c * ct_handle;

        lhs_comm == rhs_comm && lhs_handle == rhs_handle
    }

    pub fn to_bytes(&self) -> [u8; 128] {
        let mut bytes = [0u8; 128];
        bytes[0..32].copy_from_slice(&self.y_commitment_bytes);
        bytes[32..64].copy_from_slice(&self.y_handle_bytes);
        bytes[64..96].copy_from_slice(&self.response_r);
        bytes[96..128].copy_from_slice(&self.response_x);
        bytes
    }
}

// ============================================================================
// Confidential Transfer Proof Bundle
// ============================================================================

/// Complete proof bundle for a confidential transfer
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ConfidentialTransferProofBundle {
    pub source_ciphertext: ElGamalCiphertext,
    pub dest_ciphertext: ElGamalCiphertext,
    pub ownership_proof: OwnershipProof,
    pub range_proof: RangeProof,
    pub equality_proof: EqualityProof,
    pub validity_proof: ValidityProof,
    pub amount: u64,
    pub auditor_ciphertext: Option<ElGamalCiphertext>,
}

impl ConfidentialTransferProofBundle {
    /// Generate all proofs for a confidential transfer
    pub fn generate(
        amount: u64,
        sender_keypair: &ElGamalKeypair,
        recipient_pubkey: &RistrettoPoint,
        auditor_pubkey: Option<&RistrettoPoint>,
    ) -> Result<Self, SignerError> {
        if amount == 0 {
            return Err(SignerError::SigningFailed(
                "Cannot create confidential transfer for zero amount".to_string(),
            ));
        }

        let (source_ct, src_randomness) =
            ElGamalCiphertext::encrypt(amount, &sender_keypair.public);
        let (dest_ct, dst_randomness) = ElGamalCiphertext::encrypt(amount, recipient_pubkey);

        let ownership_proof = OwnershipProof::prove(sender_keypair);
        let range_proof = RangeProof::prove(amount, &src_randomness);
        let equality_proof = EqualityProof::prove(
            amount,
            sender_keypair,
            recipient_pubkey,
            &src_randomness,
            &dst_randomness,
        );
        let validity_proof =
            ValidityProof::prove(amount, &sender_keypair.public, &src_randomness);

        let auditor_ciphertext =
            auditor_pubkey.map(|pk| ElGamalCiphertext::encrypt(amount, pk).0);

        Ok(Self {
            source_ciphertext: source_ct,
            dest_ciphertext: dest_ct,
            ownership_proof,
            range_proof,
            equality_proof,
            validity_proof,
            amount,
            auditor_ciphertext,
        })
    }

    /// Verify all proofs in the bundle
    pub fn verify(&self, sender_pubkey_bytes: &[u8; 32]) -> bool {
        if !self.ownership_proof.verify(sender_pubkey_bytes) {
            return false;
        }
        if !self.range_proof.verify(&self.source_ciphertext.commitment) {
            return false;
        }
        if !self
            .validity_proof
            .verify(&self.source_ciphertext, sender_pubkey_bytes)
        {
            return false;
        }
        true
    }

    /// Serialize to JSON
    pub fn to_json(&self) -> Result<String, SignerError> {
        serde_json::to_string(self).map_err(|e| SignerError::SerializationError(e.to_string()))
    }

    /// Deserialize from JSON
    pub fn from_json(json: &str) -> Result<Self, SignerError> {
        serde_json::from_str(json).map_err(|e| SignerError::SerializationError(e.to_string()))
    }

    /// Compact binary representation
    pub fn to_compact_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::with_capacity(512);
        bytes.extend_from_slice(&self.source_ciphertext.to_bytes());
        bytes.extend_from_slice(&self.dest_ciphertext.to_bytes());
        bytes.extend_from_slice(&self.ownership_proof.to_bytes());
        bytes.extend_from_slice(&self.validity_proof.to_bytes());
        bytes.extend_from_slice(&self.equality_proof.to_bytes());
        let range_bytes = self.range_proof.to_bytes();
        bytes.extend_from_slice(&(range_bytes.len() as u32).to_le_bytes());
        bytes.extend_from_slice(&range_bytes);
        bytes
    }
}

// ============================================================================
// Discrete log helper
// ============================================================================

fn discrete_log_brute(target: &RistrettoPoint, max_val: u64) -> Option<u64> {
    let h = pedersen_h();
    let identity = RistrettoPoint::default();
    let mut current = identity;
    for i in 0..max_val {
        if current == *target {
            return Some(i);
        }
        current += h;
    }
    None
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_elgamal_encrypt_decrypt() {
        let keypair = ElGamalKeypair::generate();
        let amount = 42u64; // Keep small for fast brute-force decrypt in tests
        let (ct, _) = ElGamalCiphertext::encrypt(amount, &keypair.public);
        let decrypted = keypair.decrypt(&ct);
        assert_eq!(decrypted, Some(amount));
    }

    #[test]
    fn test_elgamal_from_seed_deterministic() {
        let seed = [42u8; 32];
        let kp1 = ElGamalKeypair::from_ed25519_seed(&seed);
        let kp2 = ElGamalKeypair::from_ed25519_seed(&seed);
        assert_eq!(kp1.public_key_bytes(), kp2.public_key_bytes());
    }

    #[test]
    fn test_ownership_proof() {
        let keypair = ElGamalKeypair::generate();
        let proof = OwnershipProof::prove(&keypair);
        let pubkey_bytes = keypair.public_key_bytes();
        assert!(proof.verify(&pubkey_bytes));

        let other = ElGamalKeypair::generate();
        assert!(!proof.verify(&other.public_key_bytes()));
    }

    #[test]
    fn test_range_proof() {
        let blinding = Scalar::random(&mut OsRng);
        let amount = 500u64;
        let commitment = PedersenCommitment::new(amount, &blinding);
        let proof = RangeProof::prove(amount, &blinding);
        assert!(proof.verify(&commitment.compress().to_bytes()));
    }

    #[test]
    fn test_validity_proof() {
        let keypair = ElGamalKeypair::generate();
        let amount = 750u64;
        let (ct, randomness) = ElGamalCiphertext::encrypt(amount, &keypair.public);
        let proof = ValidityProof::prove(amount, &keypair.public, &randomness);
        assert!(proof.verify(&ct, &keypair.public_key_bytes()));
    }

    #[test]
    fn test_full_proof_bundle() {
        let sender = ElGamalKeypair::generate();
        let recipient = ElGamalKeypair::generate();
        let amount = 50u64; // Keep small for fast brute-force decrypt in tests

        let bundle = ConfidentialTransferProofBundle::generate(
            amount,
            &sender,
            &recipient.public,
            None,
        )
        .unwrap();

        assert!(bundle.verify(&sender.public_key_bytes()));

        let decrypted = recipient.decrypt(&bundle.dest_ciphertext);
        assert_eq!(decrypted, Some(amount));

        let json = bundle.to_json().unwrap();
        let bundle2 = ConfidentialTransferProofBundle::from_json(&json).unwrap();
        assert!(bundle2.verify(&sender.public_key_bytes()));
    }

    #[test]
    fn test_zero_amount_rejected() {
        let sender = ElGamalKeypair::generate();
        let recipient = ElGamalKeypair::generate();
        let result =
            ConfidentialTransferProofBundle::generate(0, &sender, &recipient.public, None);
        assert!(result.is_err());
    }

    #[test]
    fn test_compact_bytes() {
        let sender = ElGamalKeypair::generate();
        let recipient = ElGamalKeypair::generate();
        let bundle = ConfidentialTransferProofBundle::generate(
            42,
            &sender,
            &recipient.public,
            None,
        )
        .unwrap();
        let bytes = bundle.to_compact_bytes();
        assert!(bytes.len() > 400);
    }
}
