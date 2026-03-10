//! Error types for the ZK proof engine.
//!
//! Errors are designed to be informative without leaking sensitive data.

use thiserror::Error;

/// Errors that can occur during ZK proof operations
#[derive(Error, Debug)]
pub enum ZkError {
    /// Invalid proof format or structure
    #[error("Invalid proof: {0}")]
    InvalidProof(String),

    /// Proof verification failed
    #[error("Proof verification failed: {0}")]
    VerificationFailed(String),

    /// Invalid commitment
    #[error("Invalid commitment: {0}")]
    InvalidCommitment(String),

    /// Range proof error
    #[error("Range proof error: {0}")]
    RangeError(String),

    /// Policy violation
    #[error("Policy violation: {0}")]
    PolicyViolation(String),

    /// Invalid transaction mode
    #[error("Invalid transaction mode: {0}")]
    InvalidMode(String),

    /// Missing required proof artifact
    #[error("Missing required proof: {0}")]
    MissingProof(String),

    /// Binding verification failed
    #[error("Proof binding failed: {0}")]
    BindingFailed(String),

    /// Envelope integrity check failed
    #[error("Envelope integrity check failed")]
    IntegrityFailed,

    /// Serialization error
    #[error("Serialization error: {0}")]
    SerializationError(String),

    /// Domain separation error
    #[error("Domain separation error: {0}")]
    DomainError(String),

    /// Replay detected
    #[error("Replay detected: nonce already used")]
    ReplayDetected,

    /// Invalid input
    #[error("Invalid input: {0}")]
    InvalidInput(String),

    /// Cryptographic operation failed
    #[error("Cryptographic error: {0}")]
    CryptoError(String),

    /// Mode mismatch between components
    #[error("Mode mismatch: expected {expected}, got {actual}")]
    ModeMismatch {
        expected: String,
        actual: String,
    },
}

impl From<serde_json::Error> for ZkError {
    fn from(e: serde_json::Error) -> Self {
        ZkError::SerializationError(e.to_string())
    }
}

impl From<hex::FromHexError> for ZkError {
    fn from(e: hex::FromHexError) -> Self {
        ZkError::SerializationError(format!("Hex decode error: {}", e))
    }
}

impl From<base64::DecodeError> for ZkError {
    fn from(e: base64::DecodeError) -> Self {
        ZkError::SerializationError(format!("Base64 decode error: {}", e))
    }
}
