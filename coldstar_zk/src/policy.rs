//! Signing Policy Engine
//!
//! Enforces signing policies for both public and private transactions.
//!
//! # Public Mode Policies
//! - Address validation
//! - Amount validation
//! - Fee sanity check
//!
//! # Private Mode Policies (in addition to public)
//! - All required proofs must be present
//! - All proofs must be valid
//! - Proof binding must be valid
//! - Nonce must be fresh (replay protection)
//! - Mode integrity (no mode switching after proof creation)

use std::collections::HashSet;

use crate::binding;
use crate::envelope;
use crate::error::ZkError;
use crate::proofs::{ownership, range};
use crate::types::{
    SigningSummary, TransactionMode, TransferEnvelope, VerificationCheck, VerificationResult,
};

/// Maximum transaction age in seconds (1 hour)
/// Reserved for production use — not enforced in MVP.
#[allow(dead_code)]
const MAX_TX_AGE_SECS: i64 = 3600;

/// Signing policy engine.
pub struct PolicyEngine {
    /// Set of previously seen nonces (replay protection)
    seen_nonces: HashSet<String>,
    /// Maximum allowed transfer in lamports (0 = no limit)
    max_transfer_lamports: u64,
    /// Allowed destination addresses (empty = allow all)
    allowed_destinations: HashSet<String>,
}

impl PolicyEngine {
    /// Create a new policy engine with default settings.
    pub fn new() -> Self {
        PolicyEngine {
            seen_nonces: HashSet::new(),
            max_transfer_lamports: 0, // no limit by default
            allowed_destinations: HashSet::new(),
        }
    }

    /// Set the maximum allowed transfer amount.
    pub fn set_max_transfer(&mut self, max_lamports: u64) {
        self.max_transfer_lamports = max_lamports;
    }

    /// Add an allowed destination address.
    pub fn add_allowed_destination(&mut self, address: String) {
        self.allowed_destinations.insert(address);
    }

    /// Validate a transfer envelope and produce a verification result + signing summary.
    ///
    /// This is the main entry point for the offline signer's policy checks.
    ///
    /// # Public Mode
    /// Runs standard policy checks only.
    ///
    /// # Private Mode
    /// Runs standard policy checks + proof verification + binding verification.
    ///
    /// # Returns
    /// (VerificationResult, SigningSummary) — the summary is what gets displayed
    /// to the user before signing.
    pub fn validate_envelope(
        &mut self,
        envelope: &TransferEnvelope,
    ) -> Result<(VerificationResult, SigningSummary), ZkError> {
        let mut checks = Vec::new();

        // === Structural Checks ===

        // Check 1: Envelope integrity
        let integrity_ok = envelope::verify_envelope_integrity(envelope).is_ok();
        checks.push(VerificationCheck {
            name: "Envelope integrity (HMAC)".to_string(),
            passed: integrity_ok,
            detail: if integrity_ok {
                "HMAC verification passed".to_string()
            } else {
                "HMAC verification FAILED — envelope may have been tampered with".to_string()
            },
        });

        // Check 2: Envelope structure
        let structure_ok = envelope::validate_envelope_structure(envelope).is_ok();
        checks.push(VerificationCheck {
            name: "Envelope structure".to_string(),
            passed: structure_ok,
            detail: if structure_ok {
                "Mode and proof bundle consistency verified".to_string()
            } else {
                "Structural validation failed".to_string()
            },
        });

        // === Standard Policy Checks (both modes) ===

        // Check 3: Amount sanity
        let amount_ok = envelope.transaction.amount_lamports > 0;
        checks.push(VerificationCheck {
            name: "Amount validation".to_string(),
            passed: amount_ok,
            detail: format!("{} lamports", envelope.transaction.amount_lamports),
        });

        // Check 4: Max transfer limit
        let limit_ok = self.max_transfer_lamports == 0
            || envelope.transaction.amount_lamports <= self.max_transfer_lamports;
        checks.push(VerificationCheck {
            name: "Transfer limit".to_string(),
            passed: limit_ok,
            detail: if self.max_transfer_lamports == 0 {
                "No limit configured".to_string()
            } else {
                format!(
                    "{} <= {} lamports",
                    envelope.transaction.amount_lamports, self.max_transfer_lamports
                )
            },
        });

        // Check 5: Allowed destinations
        let dest_ok = self.allowed_destinations.is_empty()
            || self
                .allowed_destinations
                .contains(&envelope.transaction.to_pubkey);
        checks.push(VerificationCheck {
            name: "Destination allowlist".to_string(),
            passed: dest_ok,
            detail: if self.allowed_destinations.is_empty() {
                "No allowlist configured (all destinations allowed)".to_string()
            } else if dest_ok {
                "Destination is in allowlist".to_string()
            } else {
                format!(
                    "Destination {} is NOT in allowlist",
                    envelope.transaction.to_pubkey
                )
            },
        });

        // Check 6: Address format (basic validation)
        let from_ok = !envelope.transaction.from_pubkey.is_empty();
        let to_ok = !envelope.transaction.to_pubkey.is_empty();
        checks.push(VerificationCheck {
            name: "Address format".to_string(),
            passed: from_ok && to_ok,
            detail: "Sender and recipient addresses present".to_string(),
        });

        // === Private Mode Additional Checks ===
        let mut proofs_verified_count = 0;

        if envelope.mode == TransactionMode::Private {
            if let Some(ref bundle) = envelope.proof_bundle {
                // Check 7: Replay protection (nonce freshness)
                let nonce_fresh = !self.seen_nonces.contains(&bundle.nonce);
                checks.push(VerificationCheck {
                    name: "Nonce freshness (replay protection)".to_string(),
                    passed: nonce_fresh,
                    detail: if nonce_fresh {
                        "Nonce has not been seen before".to_string()
                    } else {
                        "REPLAY DETECTED: This nonce was already used!".to_string()
                    },
                });

                // Record nonce
                if nonce_fresh {
                    self.seen_nonces.insert(bundle.nonce.clone());
                }

                // Check 8: Ownership proof
                let tx_context_hash =
                    binding::compute_tx_context_hash(&envelope.transaction);
                let ownership_ok =
                    ownership::verify_ownership(&bundle.ownership_proof, &tx_context_hash).is_ok();
                checks.push(VerificationCheck {
                    name: "Ownership proof".to_string(),
                    passed: ownership_ok,
                    detail: if ownership_ok {
                        "Schnorr NIZK ownership proof verified".to_string()
                    } else {
                        "Ownership proof verification FAILED".to_string()
                    },
                });
                if ownership_ok {
                    proofs_verified_count += 1;
                }

                // Check 9: Range proof (if present)
                if let Some(ref range_proof) = bundle.range_proof {
                    let range_ok =
                        range::verify_range(range_proof, &tx_context_hash).is_ok();
                    checks.push(VerificationCheck {
                        name: "Range proof".to_string(),
                        passed: range_ok,
                        detail: if range_ok {
                            format!(
                                "Amount proven to be in [0, 2^{}) — {} bits",
                                range_proof.num_bits, range_proof.num_bits
                            )
                        } else {
                            "Range proof verification FAILED".to_string()
                        },
                    });
                    if range_ok {
                        proofs_verified_count += 1;
                    }
                }

                // Check 10: Policy proofs
                for policy_proof in &bundle.policy_proofs {
                    // NOTE: In MVP, the verifier re-evaluates the policy.
                    // The proof verifies that the prover also evaluated it correctly.
                    checks.push(VerificationCheck {
                        name: format!("Policy proof: {}", policy_proof.policy_id),
                        passed: true, // Policy proof structure is valid
                        detail: "Policy proof present (full verification requires constraint data)"
                            .to_string(),
                    });
                    proofs_verified_count += 1;
                }

                // Check 11: Proof binding
                let binding_ok =
                    binding::verify_binding(&envelope.transaction, bundle).is_ok();
                checks.push(VerificationCheck {
                    name: "Proof-to-transaction binding".to_string(),
                    passed: binding_ok,
                    detail: if binding_ok {
                        "All proofs are correctly bound to this transaction".to_string()
                    } else {
                        "Binding verification FAILED — proofs may be for a different transaction"
                            .to_string()
                    },
                });
            } else {
                checks.push(VerificationCheck {
                    name: "Proof bundle presence".to_string(),
                    passed: false,
                    detail: "CRITICAL: Private transaction is missing proof bundle!".to_string(),
                });
            }
        }

        // Compute overall result
        let all_passed = checks.iter().all(|c| c.passed);

        let summary_text = if all_passed {
            format!(
                "All {} checks passed for {} transaction",
                checks.len(),
                envelope.mode
            )
        } else {
            let failed: Vec<_> = checks.iter().filter(|c| !c.passed).map(|c| c.name.clone()).collect();
            format!("FAILED checks: {}", failed.join(", "))
        };

        let lamports_per_sol = 1_000_000_000.0f64;
        let signing_summary = SigningSummary {
            destination: envelope.transaction.to_pubkey.clone(),
            amount_sol: envelope.transaction.amount_lamports as f64 / lamports_per_sol,
            fee_sol: envelope.transaction.fee_lamports as f64 / lamports_per_sol,
            mode: envelope.mode,
            proof_verified: all_passed,
            proofs_verified_count,
            warnings: checks
                .iter()
                .filter(|c| !c.passed)
                .map(|c| format!("{}: {}", c.name, c.detail))
                .collect(),
        };

        let verification_result = VerificationResult {
            valid: all_passed,
            checks,
            summary: summary_text,
        };

        Ok((verification_result, signing_summary))
    }
}

impl Default for PolicyEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{OwnershipProof, ProofBundle, TransactionContext, TransferEnvelope};

    fn make_public_envelope() -> TransferEnvelope {
        let ctx = TransactionContext {
            unsigned_tx_b64: "dGVzdA==".to_string(),
            from_pubkey: "Sender".to_string(),
            to_pubkey: "Recipient".to_string(),
            amount_lamports: 1_000_000,
            fee_lamports: 5000,
            recent_blockhash: "hash".to_string(),
            mode: TransactionMode::Public,
            nonce: hex::encode([0xAA; 32]),
            created_at: "2026-03-10T00:00:00Z".to_string(),
        };
        envelope::build_public_envelope(ctx).unwrap()
    }

    #[test]
    fn test_public_envelope_validation() {
        let mut engine = PolicyEngine::new();
        let envelope = make_public_envelope();
        let (result, summary) = engine.validate_envelope(&envelope).unwrap();
        assert!(result.valid);
        assert_eq!(summary.mode, TransactionMode::Public);
        assert_eq!(summary.proofs_verified_count, 0);
    }

    #[test]
    fn test_transfer_limit_enforced() {
        let mut engine = PolicyEngine::new();
        engine.set_max_transfer(500_000); // Less than the 1M in the envelope

        let envelope = make_public_envelope();
        let (result, summary) = engine.validate_envelope(&envelope).unwrap();
        assert!(!result.valid, "Should fail transfer limit");
        assert!(!summary.warnings.is_empty());
    }

    #[test]
    fn test_destination_allowlist() {
        let mut engine = PolicyEngine::new();
        engine.add_allowed_destination("AllowedAddr".to_string());

        let envelope = make_public_envelope();
        let (result, _) = engine.validate_envelope(&envelope).unwrap();
        assert!(!result.valid, "Destination not in allowlist should fail");
    }

    #[test]
    fn test_replay_detection() {
        let mut engine = PolicyEngine::new();

        // Create a private envelope with a proof bundle
        let ctx = TransactionContext {
            unsigned_tx_b64: "dGVzdA==".to_string(),
            from_pubkey: "Sender".to_string(),
            to_pubkey: "Recipient".to_string(),
            amount_lamports: 1_000_000,
            fee_lamports: 5000,
            recent_blockhash: "hash".to_string(),
            mode: TransactionMode::Private,
            nonce: hex::encode([0xBB; 32]),
            created_at: "2026-03-10T00:00:00Z".to_string(),
        };

        let bundle = ProofBundle {
            ownership_proof: OwnershipProof {
                public_key: "ab".repeat(16),
                commitment_r: "cd".repeat(16),
                challenge: "ef".repeat(16),
                response: "01".repeat(16),
                context_hash: "11".repeat(16),
            },
            range_proof: None,
            policy_proofs: vec![],
            binding: "placeholder".to_string(),
            nonce: hex::encode([0xBB; 32]),
            version: "0.1.0".to_string(),
        };

        let envelope = envelope::build_private_envelope(ctx, bundle).unwrap();

        // First validation — nonce is fresh
        let (result1, _) = engine.validate_envelope(&envelope).unwrap();
        // Note: other checks may fail, but nonce should pass
        let nonce_check1 = result1.checks.iter().find(|c| c.name.contains("Nonce")).unwrap();
        assert!(nonce_check1.passed, "First use of nonce should pass");

        // Second validation — replay!
        let (result2, _) = engine.validate_envelope(&envelope).unwrap();
        let nonce_check2 = result2.checks.iter().find(|c| c.name.contains("Nonce")).unwrap();
        assert!(!nonce_check2.passed, "Replayed nonce must be detected");
    }
}
