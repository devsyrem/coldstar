//! Error types for the secure signer
//!
//! All errors are designed to be informative without leaking sensitive data.

use thiserror::Error;

/// Errors that can occur during signing operations
#[derive(Error, Debug)]
pub enum SignerError {
    /// Memory locking failed - system may not support mlock or limit reached
    #[error("Failed to lock memory: {0}")]
    MemoryLockFailed(String),

    /// Key derivation failed
    #[error("Key derivation failed: {0}")]
    KeyDerivationFailed(String),

    /// Decryption failed - wrong passphrase or corrupted data
    #[error("Decryption failed - invalid passphrase or corrupted container")]
    DecryptionFailed,

    /// Invalid key format
    #[error("Invalid key format: expected 32 or 64 bytes, got {0}")]
    InvalidKeyFormat(usize),

    /// Signing operation failed
    #[error("Signing failed: {0}")]
    SigningFailed(String),

    /// Invalid transaction format
    #[error("Invalid transaction format: {0}")]
    InvalidTransaction(String),

    /// Serialization error
    #[error("Serialization error: {0}")]
    SerializationError(String),

    /// Base58 decoding error
    #[error("Base58 decoding error: {0}")]
    Base58Error(String),

    /// Base64 decoding error
    #[error("Base64 decoding error: {0}")]
    Base64Error(String),

    /// Container format error
    #[error("Invalid container format: {0}")]
    ContainerError(String),

    /// I/O error
    #[error("I/O error: {0}")]
    IoError(String),
}

impl From<std::io::Error> for SignerError {
    fn from(e: std::io::Error) -> Self {
        SignerError::IoError(e.to_string())
    }
}

impl From<base64::DecodeError> for SignerError {
    fn from(e: base64::DecodeError) -> Self {
        SignerError::Base64Error(e.to_string())
    }
}

impl From<bs58::decode::Error> for SignerError {
    fn from(e: bs58::decode::Error) -> Self {
        SignerError::Base58Error(e.to_string())
    }
}

impl From<serde_json::Error> for SignerError {
    fn from(e: serde_json::Error) -> Self {
        SignerError::SerializationError(e.to_string())
    }
}
