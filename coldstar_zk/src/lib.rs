//! Coldstar ZK — Zero-Knowledge Proof Engine for Coldstar.dev
//!
//! This crate provides zero-knowledge proof generation and verification
//! for the Coldstar cold wallet's private transaction mode.
//!
//! # Proof Systems
//!
//! - **Ownership Proof**: Schnorr NIZK proving knowledge of a signing key
//!   corresponding to a public key, without revealing the key.
//! - **Range Proof**: Bit-decomposition proof that a committed value lies
//!   within a specified range [0, 2^n), using Sigma OR-proofs per bit.
//! - **Policy Proof**: Proof that a transaction satisfies policy constraints
//!   (e.g., amount limits, authorized destinations) without revealing policy details.
//!
//! # Security Properties
//!
//! - No trusted setup required
//! - Domain separation prevents cross-context proof reuse
//! - Proofs are bound to specific transaction intent
//! - All sensitive material is zeroized after use
//! - Fiat-Shamir transform provides non-interactive proofs

pub mod binding;
pub mod commitment;
pub mod domain;
pub mod envelope;
pub mod error;
pub mod policy;
pub mod proofs;
pub mod transcript;
pub mod types;

#[cfg(feature = "ffi")]
pub mod ffi;

pub use error::ZkError;
pub use types::{ProofBundle, TransactionMode, TransferEnvelope};

/// Library version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version() {
        assert!(!VERSION.is_empty());
    }
}
