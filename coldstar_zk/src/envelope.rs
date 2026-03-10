//! Transfer Envelope — the sealed package between online and offline machines.
//!
//! The envelope contains the transaction, proof bundle (for private mode),
//! and an HMAC integrity tag to detect tampering in transit.
//!
//! # Format
//! JSON-serialized TransferEnvelope with HMAC-SHA256 integrity.
//!
//! # Security Properties
//! - Integrity: HMAC detects any modification to envelope contents
//! - Mode binding: mode is included in the HMAC computation
//! - Completeness: private envelopes must contain a valid proof bundle

use hmac::{Hmac, Mac};
use sha2::Sha256;

use crate::domain::DOMAIN_ENVELOPE_HMAC;
use crate::error::ZkError;
use crate::types::{ProofBundle, TransactionContext, TransactionMode, TransferEnvelope};

type HmacSha256 = Hmac<Sha256>;

/// Build a transfer envelope for a public transaction.
///
/// # Arguments
/// * `tx_context` - The transaction context
///
/// # Returns
/// A sealed TransferEnvelope with HMAC integrity tag.
pub fn build_public_envelope(tx_context: TransactionContext) -> Result<TransferEnvelope, ZkError> {
    if tx_context.mode != TransactionMode::Public {
        return Err(ZkError::ModeMismatch {
            expected: "public".to_string(),
            actual: tx_context.mode.to_string(),
        });
    }

    let mut envelope = TransferEnvelope {
        version: "1.0.0".to_string(),
        mode: TransactionMode::Public,
        created_at: tx_context.created_at.clone(),
        transaction: tx_context,
        proof_bundle: None,
        integrity: String::new(),
    };

    envelope.integrity = compute_envelope_hmac(&envelope)?;
    Ok(envelope)
}

/// Build a transfer envelope for a private transaction.
///
/// # Arguments
/// * `tx_context` - The transaction context (must have mode=private)
/// * `proof_bundle` - The proof bundle (must have valid binding)
///
/// # Returns
/// A sealed TransferEnvelope with HMAC integrity tag.
pub fn build_private_envelope(
    tx_context: TransactionContext,
    proof_bundle: ProofBundle,
) -> Result<TransferEnvelope, ZkError> {
    if tx_context.mode != TransactionMode::Private {
        return Err(ZkError::ModeMismatch {
            expected: "private".to_string(),
            actual: tx_context.mode.to_string(),
        });
    }

    // Verify proof bundle has a binding
    if proof_bundle.binding.is_empty() {
        return Err(ZkError::MissingProof(
            "Proof bundle must have a binding before envelope creation".into(),
        ));
    }

    let mut envelope = TransferEnvelope {
        version: "1.0.0".to_string(),
        mode: TransactionMode::Private,
        created_at: tx_context.created_at.clone(),
        transaction: tx_context,
        proof_bundle: Some(proof_bundle),
        integrity: String::new(),
    };

    envelope.integrity = compute_envelope_hmac(&envelope)?;
    Ok(envelope)
}

/// Verify the integrity of a transfer envelope.
///
/// # Arguments
/// * `envelope` - The envelope to verify
///
/// # Returns
/// Ok(()) if integrity check passes, Err if tampered.
pub fn verify_envelope_integrity(envelope: &TransferEnvelope) -> Result<(), ZkError> {
    let expected_hmac = compute_envelope_hmac(envelope)?;
    if envelope.integrity != expected_hmac {
        return Err(ZkError::IntegrityFailed);
    }
    Ok(())
}

/// Validate that an envelope is well-formed for its mode.
///
/// - Public envelopes must NOT have proof bundles
/// - Private envelopes MUST have proof bundles
/// - Mode must match between envelope and transaction context
pub fn validate_envelope_structure(envelope: &TransferEnvelope) -> Result<(), ZkError> {
    // Mode consistency
    if envelope.mode != envelope.transaction.mode {
        return Err(ZkError::ModeMismatch {
            expected: envelope.mode.to_string(),
            actual: envelope.transaction.mode.to_string(),
        });
    }

    match envelope.mode {
        TransactionMode::Public => {
            if envelope.proof_bundle.is_some() {
                return Err(ZkError::InvalidMode(
                    "Public envelope must not contain proof bundle".into(),
                ));
            }
        }
        TransactionMode::Private => {
            if envelope.proof_bundle.is_none() {
                return Err(ZkError::MissingProof(
                    "Private envelope must contain proof bundle".into(),
                ));
            }
        }
    }

    Ok(())
}

/// Serialize an envelope to JSON.
pub fn serialize_envelope(envelope: &TransferEnvelope) -> Result<String, ZkError> {
    serde_json::to_string_pretty(envelope).map_err(|e| ZkError::SerializationError(e.to_string()))
}

/// Deserialize an envelope from JSON.
pub fn deserialize_envelope(json: &str) -> Result<TransferEnvelope, ZkError> {
    serde_json::from_str(json).map_err(|e| ZkError::SerializationError(e.to_string()))
}

/// Compute the HMAC-SHA256 integrity tag for an envelope.
///
/// The HMAC key is derived from the domain tag + envelope version.
/// In production, this should use a shared secret between online and offline machines.
///
/// # SECURITY NOTE
/// The MVP uses a domain-derived key. This provides tamper detection
/// against accidental modification but NOT against a sophisticated attacker
/// who knows the key derivation. In production, use a pre-shared secret.
fn compute_envelope_hmac(envelope: &TransferEnvelope) -> Result<String, ZkError> {
    // Derive HMAC key from domain tag
    // SECURITY: In production, replace with pre-shared secret
    let mut key_material = Vec::new();
    key_material.extend_from_slice(DOMAIN_ENVELOPE_HMAC);
    key_material.extend_from_slice(envelope.version.as_bytes());

    let mut mac = HmacSha256::new_from_slice(&key_material)
        .map_err(|e| ZkError::CryptoError(format!("HMAC init failed: {}", e)))?;

    // Feed envelope contents (excluding the integrity field itself)
    mac.update(envelope.version.as_bytes());
    mac.update(envelope.mode.as_str().as_bytes());
    mac.update(envelope.created_at.as_bytes());
    mac.update(envelope.transaction.unsigned_tx_b64.as_bytes());
    mac.update(envelope.transaction.from_pubkey.as_bytes());
    mac.update(envelope.transaction.to_pubkey.as_bytes());
    mac.update(&envelope.transaction.amount_lamports.to_le_bytes());
    mac.update(&envelope.transaction.fee_lamports.to_le_bytes());
    mac.update(envelope.transaction.recent_blockhash.as_bytes());
    mac.update(envelope.transaction.nonce.as_bytes());

    if let Some(ref bundle) = envelope.proof_bundle {
        mac.update(b":proof_bundle:");
        let bundle_json = serde_json::to_string(bundle)
            .map_err(|e| ZkError::SerializationError(e.to_string()))?;
        mac.update(bundle_json.as_bytes());
    }

    let result = mac.finalize();
    Ok(hex::encode(result.into_bytes()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::OwnershipProof;

    fn make_public_context() -> TransactionContext {
        TransactionContext {
            unsigned_tx_b64: "dGVzdA==".to_string(),
            from_pubkey: "Sender111".to_string(),
            to_pubkey: "Recip111".to_string(),
            amount_lamports: 1_000_000_000,
            fee_lamports: 5000,
            recent_blockhash: "Hash111".to_string(),
            mode: TransactionMode::Public,
            nonce: "aa".repeat(32),
            created_at: "2026-03-10T00:00:00Z".to_string(),
        }
    }

    fn make_private_context() -> TransactionContext {
        let mut ctx = make_public_context();
        ctx.mode = TransactionMode::Private;
        ctx
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
            binding: "binding_hash_placeholder".to_string(),
            nonce: "ff".repeat(32),
            version: "0.1.0".to_string(),
        }
    }

    #[test]
    fn test_public_envelope_roundtrip() {
        let ctx = make_public_context();
        let envelope = build_public_envelope(ctx).unwrap();
        assert_eq!(envelope.mode, TransactionMode::Public);
        assert!(envelope.proof_bundle.is_none());

        let json = serialize_envelope(&envelope).unwrap();
        let restored = deserialize_envelope(&json).unwrap();
        assert_eq!(restored.mode, TransactionMode::Public);

        assert!(verify_envelope_integrity(&restored).is_ok());
        assert!(validate_envelope_structure(&restored).is_ok());
    }

    #[test]
    fn test_private_envelope_roundtrip() {
        let ctx = make_private_context();
        let bundle = make_test_bundle();
        let envelope = build_private_envelope(ctx, bundle).unwrap();
        assert_eq!(envelope.mode, TransactionMode::Private);
        assert!(envelope.proof_bundle.is_some());

        let json = serialize_envelope(&envelope).unwrap();
        let restored = deserialize_envelope(&json).unwrap();
        assert!(verify_envelope_integrity(&restored).is_ok());
        assert!(validate_envelope_structure(&restored).is_ok());
    }

    #[test]
    fn test_tampered_envelope_detected() {
        let ctx = make_public_context();
        let mut envelope = build_public_envelope(ctx).unwrap();

        // Tamper with amount
        envelope.transaction.amount_lamports = 999_999;

        assert!(verify_envelope_integrity(&envelope).is_err());
    }

    #[test]
    fn test_public_with_proofs_rejected() {
        let mut envelope = TransferEnvelope {
            version: "1.0.0".to_string(),
            mode: TransactionMode::Public,
            created_at: "2026-03-10".to_string(),
            transaction: make_public_context(),
            proof_bundle: Some(make_test_bundle()),
            integrity: String::new(),
        };
        assert!(validate_envelope_structure(&envelope).is_err());
    }

    #[test]
    fn test_private_without_proofs_rejected() {
        let envelope = TransferEnvelope {
            version: "1.0.0".to_string(),
            mode: TransactionMode::Private,
            created_at: "2026-03-10".to_string(),
            transaction: make_private_context(),
            proof_bundle: None,
            integrity: String::new(),
        };
        assert!(validate_envelope_structure(&envelope).is_err());
    }

    #[test]
    fn test_mode_mismatch_rejected() {
        let mut ctx = make_public_context();
        ctx.mode = TransactionMode::Private; // mismatch with envelope mode
        let envelope = TransferEnvelope {
            version: "1.0.0".to_string(),
            mode: TransactionMode::Public,
            created_at: "2026-03-10".to_string(),
            transaction: ctx,
            proof_bundle: None,
            integrity: String::new(),
        };
        assert!(validate_envelope_structure(&envelope).is_err());
    }
}
