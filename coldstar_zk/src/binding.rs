//! Proof-to-Transaction Binding
//!
//! Cryptographically binds a proof bundle to a specific transaction,
//! preventing proof repurposing across different transactions.
//!
//! The binding is a SHA-256 hash over:
//! - Domain tag (DOMAIN_BINDING)
//! - Transaction bytes hash
//! - Proof bundle nonce
//! - Each proof's context hash
//! - Transaction mode
//!
//! # Security Properties
//! - Fresh nonce per transaction prevents replay
//! - Transaction hash inclusion prevents proof repurposing
//! - Domain separation prevents cross-context collisions

use sha2::{Digest, Sha256};

use crate::domain::DOMAIN_BINDING;
use crate::error::ZkError;
use crate::types::{ProofBundle, TransactionContext, TransactionMode};

/// Compute the binding hash that ties a proof bundle to a transaction.
///
/// # Arguments
/// * `tx_context` - The transaction context
/// * `bundle` - The proof bundle
///
/// # Returns
/// Hex-encoded SHA-256 binding hash
pub fn compute_binding(tx_context: &TransactionContext, bundle: &ProofBundle) -> String {
    let mut hasher = Sha256::new();

    // Domain separation
    hasher.update(DOMAIN_BINDING);

    // Transaction identity
    hasher.update(b":tx_bytes:");
    hasher.update(tx_context.unsigned_tx_b64.as_bytes());

    // Transaction metadata
    hasher.update(b":from:");
    hasher.update(tx_context.from_pubkey.as_bytes());
    hasher.update(b":to:");
    hasher.update(tx_context.to_pubkey.as_bytes());
    hasher.update(b":amount:");
    hasher.update(tx_context.amount_lamports.to_le_bytes());
    hasher.update(b":fee:");
    hasher.update(tx_context.fee_lamports.to_le_bytes());
    hasher.update(b":blockhash:");
    hasher.update(tx_context.recent_blockhash.as_bytes());

    // Mode
    hasher.update(b":mode:");
    hasher.update(tx_context.mode.as_str().as_bytes());

    // Nonce
    hasher.update(b":nonce:");
    hasher.update(bundle.nonce.as_bytes());

    // Proof context hashes
    hasher.update(b":ownership_ctx:");
    hasher.update(bundle.ownership_proof.context_hash.as_bytes());

    if let Some(ref range_proof) = bundle.range_proof {
        hasher.update(b":range_ctx:");
        hasher.update(range_proof.context_hash.as_bytes());
    }

    for policy_proof in &bundle.policy_proofs {
        hasher.update(b":policy_ctx:");
        hasher.update(policy_proof.policy_id.as_bytes());
        hasher.update(b":");
        hasher.update(policy_proof.context_hash.as_bytes());
    }

    // Timestamp
    hasher.update(b":created_at:");
    hasher.update(tx_context.created_at.as_bytes());

    hex::encode(hasher.finalize())
}

/// Verify that a proof bundle's binding matches the transaction context.
///
/// # Arguments
/// * `tx_context` - The transaction context
/// * `bundle` - The proof bundle (with binding field set)
///
/// # Returns
/// Ok(()) if the binding is valid, Err if not.
pub fn verify_binding(tx_context: &TransactionContext, bundle: &ProofBundle) -> Result<(), ZkError> {
    // Mode must be private for proof bundles
    if tx_context.mode != TransactionMode::Private {
        return Err(ZkError::ModeMismatch {
            expected: "private".to_string(),
            actual: tx_context.mode.to_string(),
        });
    }

    // Recompute binding
    let expected_binding = compute_binding(tx_context, bundle);

    if bundle.binding != expected_binding {
        return Err(ZkError::BindingFailed(
            "Proof bundle binding does not match transaction context — \
             proofs may have been generated for a different transaction"
                .into(),
        ));
    }

    Ok(())
}

/// Generate a fresh nonce for proof binding.
///
/// Uses OsRng for cryptographic randomness.
/// Returns hex-encoded 32 random bytes.
pub fn generate_nonce() -> String {
    use rand_core::OsRng;
    use rand::RngCore;
    let mut nonce = [0u8; 32];
    OsRng.fill_bytes(&mut nonce);
    hex::encode(nonce)
}

/// Compute a context hash for the transaction (used as input to proofs).
///
/// This provides a compact representation of the transaction that proofs
/// can reference without including the full transaction bytes.
pub fn compute_tx_context_hash(tx_context: &TransactionContext) -> Vec<u8> {
    let mut hasher = Sha256::new();
    hasher.update(crate::domain::DOMAIN_TX_CONTEXT);
    hasher.update(tx_context.unsigned_tx_b64.as_bytes());
    hasher.update(tx_context.from_pubkey.as_bytes());
    hasher.update(tx_context.to_pubkey.as_bytes());
    hasher.update(tx_context.amount_lamports.to_le_bytes());
    hasher.update(tx_context.nonce.as_bytes());
    hasher.finalize().to_vec()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{OwnershipProof, TransactionMode};

    fn make_test_context() -> TransactionContext {
        TransactionContext {
            unsigned_tx_b64: "dGVzdA==".to_string(),
            from_pubkey: "SenderPubkey111111111111111111111111111111111".to_string(),
            to_pubkey: "RecipPubkey1111111111111111111111111111111111".to_string(),
            amount_lamports: 1_000_000_000,
            fee_lamports: 5000,
            recent_blockhash: "Blockhash111111111111111111111111111111111111".to_string(),
            mode: TransactionMode::Private,
            nonce: "aa".repeat(32),
            created_at: "2026-03-10T00:00:00Z".to_string(),
        }
    }

    fn make_test_bundle() -> ProofBundle {
        ProofBundle {
            ownership_proof: OwnershipProof {
                public_key: "ab".repeat(16),
                commitment_r: "cd".repeat(16),
                challenge: "ef".repeat(16),
                response: "01".repeat(16),
                context_hash: "11".repeat(16),
            },
            range_proof: None,
            policy_proofs: vec![],
            binding: String::new(), // Will be set
            nonce: "ff".repeat(32),
            version: "0.1.0".to_string(),
        }
    }

    #[test]
    fn test_binding_deterministic() {
        let ctx = make_test_context();
        let bundle = make_test_bundle();
        let b1 = compute_binding(&ctx, &bundle);
        let b2 = compute_binding(&ctx, &bundle);
        assert_eq!(b1, b2, "Binding must be deterministic");
    }

    #[test]
    fn test_binding_changes_with_amount() {
        let mut ctx1 = make_test_context();
        let mut ctx2 = make_test_context();
        ctx2.amount_lamports = 2_000_000_000;

        let bundle = make_test_bundle();
        let b1 = compute_binding(&ctx1, &bundle);
        let b2 = compute_binding(&ctx2, &bundle);
        assert_ne!(b1, b2, "Different amounts must produce different bindings");
    }

    #[test]
    fn test_binding_verification() {
        let ctx = make_test_context();
        let mut bundle = make_test_bundle();
        bundle.binding = compute_binding(&ctx, &bundle);
        assert!(verify_binding(&ctx, &bundle).is_ok());
    }

    #[test]
    fn test_binding_rejects_tampered() {
        let ctx = make_test_context();
        let mut bundle = make_test_bundle();
        bundle.binding = compute_binding(&ctx, &bundle);

        // Tamper with binding
        bundle.binding = "00".repeat(32);
        assert!(verify_binding(&ctx, &bundle).is_err());
    }

    #[test]
    fn test_binding_rejects_public_mode() {
        let mut ctx = make_test_context();
        ctx.mode = TransactionMode::Public;
        let bundle = make_test_bundle();
        assert!(verify_binding(&ctx, &bundle).is_err());
    }

    #[test]
    fn test_nonce_uniqueness() {
        let n1 = generate_nonce();
        let n2 = generate_nonce();
        assert_ne!(n1, n2, "Nonces must be unique");
        assert_eq!(n1.len(), 64, "Nonce must be 32 bytes hex = 64 chars");
    }
}
