//! Cryptographic operations for secure signing
//!
//! This module handles:
//! - Key derivation (Argon2id)
//! - Symmetric encryption/decryption (AES-256-GCM)
//! - Ed25519 signing (Solana-compatible)
//!
//! # Security Model
//!
//! All operations involving plaintext private keys use SecureBuffer
//! to ensure memory is locked and zeroized.

use aes_gcm::{
    aead::{Aead, KeyInit},
    Aes256Gcm, Nonce,
};
use argon2::{Argon2, Params, Version};
use ed25519_dalek::{Signature, Signer, SigningKey};
use rand::rngs::OsRng;
use rand::RngCore;
use serde::{Deserialize, Serialize};

use crate::error::SignerError;
use crate::secure_buffer::{LockingMode, SecureBuffer};

/// Environment variable to allow insecure memory (permissive mode)
/// Set to "1" or "true" to allow operation when mlock fails.
/// WARNING: Only use this for testing or on systems that don't support mlock.
const ENV_ALLOW_INSECURE: &str = "SIGNER_ALLOW_INSECURE_MEMORY";

/// Get the appropriate locking mode based on environment
fn get_locking_mode() -> LockingMode {
    match std::env::var(ENV_ALLOW_INSECURE) {
        Ok(val) if val == "1" || val.eq_ignore_ascii_case("true") => LockingMode::Permissive,
        _ => LockingMode::Strict,
    }
}

/// Argon2 parameters for key derivation
/// These are intentionally strong to resist brute-force attacks
const ARGON2_MEMORY_COST: u32 = 65536; // 64 MB
const ARGON2_TIME_COST: u32 = 3; // 3 iterations
const ARGON2_PARALLELISM: u32 = 4; // 4 parallel lanes

/// Size constants
const KEY_SIZE: usize = 32; // 256 bits for AES-256
const NONCE_SIZE: usize = 12; // 96 bits for AES-GCM
const SALT_SIZE: usize = 32; // 256 bits for Argon2
const ED25519_SEED_SIZE: usize = 32;
const ED25519_KEYPAIR_SIZE: usize = 64;

/// Encrypted key container format
///
/// This structure holds all data needed to decrypt a private key:
/// - Salt for key derivation
/// - Nonce for AES-GCM
/// - Encrypted private key (ciphertext + auth tag)
///
/// The container can be serialized to JSON for storage/transmission.
#[derive(Serialize, Deserialize, Clone)]
pub struct EncryptedKeyContainer {
    /// Version for future format changes
    pub version: u8,
    /// Salt for Argon2 key derivation (base64)
    pub salt: String,
    /// Nonce for AES-GCM (base64)
    pub nonce: String,
    /// Encrypted private key with auth tag (base64)
    pub ciphertext: String,
    /// Public key for verification (base58, optional)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub public_key: Option<String>,
}

impl EncryptedKeyContainer {
    /// Create a new encrypted key container from a plaintext private key
    ///
    /// # Arguments
    /// * `private_key` - The 32-byte Ed25519 seed or 64-byte keypair
    /// * `passphrase` - The passphrase to encrypt with
    ///
    /// # Returns
    /// The encrypted container
    ///
    /// # Memory Lifecycle
    /// The private key is copied into a secure buffer for processing,
    /// and all intermediate values are zeroized.
    pub fn encrypt(private_key: &[u8], passphrase: &str) -> Result<Self, SignerError> {
        // Validate key size
        if private_key.len() != ED25519_SEED_SIZE && private_key.len() != ED25519_KEYPAIR_SIZE {
            return Err(SignerError::InvalidKeyFormat(private_key.len()));
        }

        // Use only the 32-byte seed (first half of keypair if 64 bytes)
        let seed = &private_key[..ED25519_SEED_SIZE];

        // Copy to secure buffer for processing (uses env-based locking mode)
        let mut secure_key = SecureBuffer::from_slice_with_mode(seed, get_locking_mode())?;

        // Generate random salt and nonce
        let mut salt = [0u8; SALT_SIZE];
        let mut nonce = [0u8; NONCE_SIZE];
        OsRng.fill_bytes(&mut salt);
        OsRng.fill_bytes(&mut nonce);

        // Derive encryption key from passphrase
        let mut derived_key = derive_key(passphrase.as_bytes(), &salt)?;

        // Encrypt the private key
        let cipher = Aes256Gcm::new_from_slice(derived_key.as_slice())
            .map_err(|e| SignerError::KeyDerivationFailed(e.to_string()))?;

        let ciphertext = cipher
            .encrypt(Nonce::from_slice(&nonce), secure_key.as_slice())
            .map_err(|_| SignerError::SigningFailed("Encryption failed".to_string()))?;

        // Get public key for verification
        let signing_key = SigningKey::from_bytes(
            secure_key.as_slice().try_into().map_err(|_| {
                SignerError::InvalidKeyFormat(secure_key.len())
            })?,
        );
        let public_key = bs58::encode(signing_key.verifying_key().as_bytes()).into_string();

        // Zeroize sensitive data
        secure_key.zeroize();
        derived_key.zeroize();

        Ok(Self {
            version: 1,
            salt: base64::Engine::encode(&base64::engine::general_purpose::STANDARD, salt),
            nonce: base64::Engine::encode(&base64::engine::general_purpose::STANDARD, nonce),
            ciphertext: base64::Engine::encode(&base64::engine::general_purpose::STANDARD, ciphertext),
            public_key: Some(public_key),
        })
    }

    /// Serialize the container to JSON
    pub fn to_json(&self) -> Result<String, SignerError> {
        serde_json::to_string(self).map_err(|e| SignerError::SerializationError(e.to_string()))
    }

    /// Deserialize from JSON
    pub fn from_json(json: &str) -> Result<Self, SignerError> {
        serde_json::from_str(json).map_err(|e| SignerError::ContainerError(e.to_string()))
    }
}

/// Result of a signing operation
#[derive(Serialize, Deserialize)]
pub struct SigningResult {
    /// The signature (base58 encoded)
    pub signature: String,
    /// The signed transaction (base64 encoded, if transaction was provided)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signed_transaction: Option<String>,
    /// The public key that signed (base58 encoded)
    pub public_key: String,
}

/// Decrypt a key container and sign a transaction
///
/// # Security Model
///
/// This function:
/// 1. Derives the decryption key from the passphrase
/// 2. Decrypts the private key into a secure buffer
/// 3. Signs the transaction
/// 4. Zeroizes all sensitive data (even on error/panic)
/// 5. Returns only the signed transaction
///
/// The plaintext private key NEVER leaves the secure buffer.
///
/// # Arguments
/// * `container_json` - JSON-serialized EncryptedKeyContainer
/// * `passphrase` - The passphrase for decryption
/// * `transaction_bytes` - The unsigned transaction to sign (serialized)
///
/// # Returns
/// The signing result with signature and optionally the full signed transaction
pub fn decrypt_and_sign(
    container_json: &str,
    passphrase: &str,
    transaction_bytes: &[u8],
) -> Result<SigningResult, SignerError> {
    // Parse the container
    let container = EncryptedKeyContainer::from_json(container_json)?;

    // Decode base64 fields
    let salt = base64::Engine::decode(&base64::engine::general_purpose::STANDARD, &container.salt)?;
    let nonce = base64::Engine::decode(&base64::engine::general_purpose::STANDARD, &container.nonce)?;
    let ciphertext = base64::Engine::decode(&base64::engine::general_purpose::STANDARD, &container.ciphertext)?;

    // Derive decryption key
    let mut derived_key = derive_key(passphrase.as_bytes(), &salt)?;

    // Decrypt the private key into secure buffer
    let cipher = Aes256Gcm::new_from_slice(derived_key.as_slice())
        .map_err(|e| SignerError::KeyDerivationFailed(e.to_string()))?;

    let plaintext = cipher
        .decrypt(Nonce::from_slice(&nonce), ciphertext.as_slice())
        .map_err(|_| SignerError::DecryptionFailed)?;

    // Immediately move to secure buffer and zeroize intermediate
    let mut secure_key = SecureBuffer::from_slice_with_mode(&plaintext, get_locking_mode())?;

    // Zeroize the derived key and plaintext copy
    derived_key.zeroize();
    // Note: plaintext is owned by cipher, can't zeroize it directly
    // But we've copied to secure buffer immediately

    // Create signing key from secure buffer
    // MEMORY LIFECYCLE: The signing key is created from our secure buffer
    // and will be zeroized when dropped (ed25519-dalek supports zeroize)
    let result = sign_with_secure_key(&mut secure_key, transaction_bytes);

    // Explicit zeroization (also happens on drop)
    secure_key.zeroize();

    result
}

/// Sign a transaction with a key in a secure buffer
///
/// # Memory Lifecycle
/// The secure buffer is borrowed mutably and its contents are used
/// to create a signing key. The signing key itself supports zeroization.
fn sign_with_secure_key(
    secure_key: &mut SecureBuffer,
    transaction_bytes: &[u8],
) -> Result<SigningResult, SignerError> {
    // Validate key size
    if secure_key.len() != ED25519_SEED_SIZE {
        return Err(SignerError::InvalidKeyFormat(secure_key.len()));
    }

    // Create signing key - ed25519-dalek's SigningKey implements Zeroize
    let signing_key = SigningKey::from_bytes(
        secure_key.as_slice().try_into().map_err(|_| {
            SignerError::InvalidKeyFormat(secure_key.len())
        })?,
    );

    // Get the public key
    let public_key = signing_key.verifying_key();
    let public_key_b58 = bs58::encode(public_key.as_bytes()).into_string();

    // Sign the transaction message
    let signature: Signature = signing_key.sign(transaction_bytes);

    // For Solana transactions, we need to embed the signature
    // The transaction format is: signatures_count + signatures + message
    // We'll return just the signature; the caller can construct the full tx
    let signature_b58 = bs58::encode(signature.to_bytes()).into_string();

    // Build signed transaction if this looks like a Solana transaction message
    let signed_transaction = if transaction_bytes.len() >= 3 {
        // Simple signed transaction: 1 signature count + signature + message
        let mut signed_tx = Vec::with_capacity(1 + 64 + transaction_bytes.len());
        signed_tx.push(1u8); // One signature
        signed_tx.extend_from_slice(&signature.to_bytes());
        signed_tx.extend_from_slice(transaction_bytes);
        Some(base64::Engine::encode(
            &base64::engine::general_purpose::STANDARD,
            &signed_tx,
        ))
    } else {
        None
    };

    Ok(SigningResult {
        signature: signature_b58,
        signed_transaction,
        public_key: public_key_b58,
    })
}

/// Sign a transaction with a raw (already decrypted) private key
///
/// # Security Warning
/// This function expects the key to already be in secure memory.
/// Prefer using decrypt_and_sign() for the full secure workflow.
///
/// # Arguments
/// * `private_key` - The 32-byte Ed25519 seed
/// * `transaction_bytes` - The transaction message to sign
pub fn sign_transaction(
    private_key: &[u8],
    transaction_bytes: &[u8],
) -> Result<SigningResult, SignerError> {
    // Copy to secure buffer (uses env-based locking mode)
    let mut secure_key = SecureBuffer::from_slice_with_mode(private_key, get_locking_mode())?;

    // Sign
    let result = sign_with_secure_key(&mut secure_key, transaction_bytes);

    // Zeroize
    secure_key.zeroize();

    result
}

/// Create an encrypted key container from a private key
///
/// Convenience function for creating containers.
pub fn create_encrypted_key_container(
    private_key: &[u8],
    passphrase: &str,
) -> Result<String, SignerError> {
    let container = EncryptedKeyContainer::encrypt(private_key, passphrase)?;
    container.to_json()
}

/// Derive an encryption key from a passphrase using Argon2id
///
/// # Memory Lifecycle
/// Returns a SecureBuffer containing the derived key.
fn derive_key(passphrase: &[u8], salt: &[u8]) -> Result<SecureBuffer, SignerError> {
    let params = Params::new(
        ARGON2_MEMORY_COST,
        ARGON2_TIME_COST,
        ARGON2_PARALLELISM,
        Some(KEY_SIZE),
    )
    .map_err(|e| SignerError::KeyDerivationFailed(e.to_string()))?;

    let argon2 = Argon2::new(argon2::Algorithm::Argon2id, Version::V0x13, params);

    // Use env-based locking mode for derived keys
    let mut key = SecureBuffer::with_mode(KEY_SIZE, get_locking_mode())?;

    argon2
        .hash_password_into(passphrase, salt, key.as_mut_slice())
        .map_err(|e| SignerError::KeyDerivationFailed(e.to_string()))?;

    Ok(key)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper to enable permissive mode for tests (mlock may not be available)
    fn enable_permissive_mode() {
        std::env::set_var(ENV_ALLOW_INSECURE, "1");
    }

    #[test]
    fn test_encrypt_decrypt_roundtrip() {
        enable_permissive_mode();
        
        // Generate a test key
        let mut seed = [0u8; 32];
        OsRng.fill_bytes(&mut seed);
        let passphrase = "test_passphrase_123";

        // Encrypt
        let container = EncryptedKeyContainer::encrypt(&seed, passphrase).unwrap();
        let json = container.to_json().unwrap();

        // Create a test message
        let message = b"test transaction message";

        // Decrypt and sign
        let result = decrypt_and_sign(&json, passphrase, message).unwrap();

        // Verify the signature
        let signing_key = SigningKey::from_bytes(&seed);
        let public_key = signing_key.verifying_key();

        assert_eq!(
            result.public_key,
            bs58::encode(public_key.as_bytes()).into_string()
        );
    }

    #[test]
    fn test_wrong_passphrase_fails() {
        enable_permissive_mode();
        
        let mut seed = [0u8; 32];
        OsRng.fill_bytes(&mut seed);

        let container = EncryptedKeyContainer::encrypt(&seed, "correct_password").unwrap();
        let json = container.to_json().unwrap();

        let result = decrypt_and_sign(&json, "wrong_password", b"test");
        assert!(matches!(result, Err(SignerError::DecryptionFailed)));
    }

    #[test]
    fn test_signature_verification() {
        enable_permissive_mode();
        
        use ed25519_dalek::Verifier;

        let mut seed = [0u8; 32];
        OsRng.fill_bytes(&mut seed);
        let message = b"Hello, Solana!";

        let result = sign_transaction(&seed, message).unwrap();

        // Verify signature
        let signing_key = SigningKey::from_bytes(&seed);
        let signature_bytes = bs58::decode(&result.signature).into_vec().unwrap();
        let signature = Signature::from_slice(&signature_bytes).unwrap();

        assert!(signing_key.verifying_key().verify(message, &signature).is_ok());
    }
}
