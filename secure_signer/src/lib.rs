//! Solana Secure Signer - A memory-safe signing core for Solana transactions
//!
//! This library provides secure Ed25519 signing for Solana transactions with:
//! - Memory-locked key storage (mlock/VirtualLock)
//! - Automatic zeroization of sensitive data
//! - Panic-safe cleanup
//! - No plaintext key exposure outside signing function
//!
//! # Security Model
//!
//! The private key is:
//! 1. Received as an encrypted container (AES-256-GCM)
//! 2. Decrypted directly into a locked memory buffer
//! 3. Used for signing within the secure context
//! 4. Immediately zeroized after use (even on error/panic)
//!
//! The plaintext key NEVER:
//! - Leaves the locked memory buffer
//! - Gets logged or written to disk
//! - Gets swapped to disk (memory is locked)
//! - Survives beyond the signing function scope

pub mod crypto;
pub mod error;
pub mod secure_buffer;

#[cfg(feature = "ffi")]
pub mod ffi;

pub use crypto::{
    create_encrypted_key_container, decrypt_and_sign, sign_transaction, EncryptedKeyContainer,
    SigningResult,
};
pub use error::SignerError;
pub use secure_buffer::{LockingMode, SecureBuffer};

/// Library version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Re-export for convenience
pub mod prelude {
    pub use crate::crypto::{
        create_encrypted_key_container, decrypt_and_sign, EncryptedKeyContainer,
    };
    pub use crate::error::SignerError;
    pub use crate::secure_buffer::SecureBuffer;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version() {
        assert!(!VERSION.is_empty());
    }
}
