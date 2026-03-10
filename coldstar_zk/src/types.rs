//! Core types for the Coldstar ZK proof system.

use serde::{Deserialize, Serialize};

/// Transaction mode — explicitly chosen by the user before signing.
///
/// SECURITY: This enum must never have a default. The user must
/// explicitly select a mode. Ambiguous states are rejected.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TransactionMode {
    /// Standard transaction — no ZK proofs required.
    /// Uses the normal Coldstar signing pipeline.
    Public,
    /// Private transaction — ZK proofs required before signing.
    /// The signer will reject if proofs are missing or invalid.
    Private,
}

impl TransactionMode {
    /// Parse a mode string. Returns None for invalid strings.
    /// Only accepts exact matches: "public" or "private".
    pub fn from_str_strict(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "public" => Some(TransactionMode::Public),
            "private" => Some(TransactionMode::Private),
            _ => None,
        }
    }

    /// Returns the mode as a display string.
    pub fn as_str(&self) -> &'static str {
        match self {
            TransactionMode::Public => "public",
            TransactionMode::Private => "private",
        }
    }

    /// Returns true if this mode requires ZK proofs.
    pub fn requires_proofs(&self) -> bool {
        matches!(self, TransactionMode::Private)
    }
}

impl std::fmt::Display for TransactionMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// Transaction context — metadata about the transaction being signed.
/// This is used to bind proofs to a specific transaction.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionContext {
    /// The unsigned transaction bytes (base64-encoded)
    pub unsigned_tx_b64: String,
    /// Sender public key (base58)
    pub from_pubkey: String,
    /// Recipient public key (base58)
    pub to_pubkey: String,
    /// Transfer amount in lamports
    pub amount_lamports: u64,
    /// Transaction fee in lamports
    pub fee_lamports: u64,
    /// Recent blockhash (base58)
    pub recent_blockhash: String,
    /// Transaction mode
    pub mode: TransactionMode,
    /// Unique nonce for this transaction (hex-encoded, 32 bytes)
    pub nonce: String,
    /// ISO-8601 timestamp of transaction creation
    pub created_at: String,
}

/// A Schnorr NIZK proof of wallet ownership.
///
/// Proves knowledge of the secret key `x` such that `X = x*G`
/// without revealing `x`.
///
/// Protocol (Fiat-Shamir):
///   1. Prover picks random k, computes R = k*G
///   2. c = H(domain || X || R || context)
///   3. s = k + c*x
///   Verifier checks: s*G == R + c*X
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OwnershipProof {
    /// Public key being proven (compressed Ristretto, hex)
    pub public_key: String,
    /// Commitment R = k*G (compressed Ristretto, hex)
    pub commitment_r: String,
    /// Challenge c (scalar, hex)
    pub challenge: String,
    /// Response s = k + c*x (scalar, hex)
    pub response: String,
    /// Context data hash that was included in the challenge (hex)
    pub context_hash: String,
}

/// A single bit proof within a range proof.
///
/// Proves that a committed bit is either 0 or 1 using
/// a Sigma OR-proof (CDS technique).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BitProof {
    /// Bit commitment C_i = b_i*G + r_i*H (compressed Ristretto, hex)
    pub commitment: String,
    /// Challenge for branch 0: e0 (scalar, hex)
    pub e0: String,
    /// Response for branch 0: s0 (scalar, hex)
    pub s0: String,
    /// Challenge for branch 1: e1 (scalar, hex)
    pub e1: String,
    /// Response for branch 1: s1 (scalar, hex)
    pub s1: String,
}

/// A range proof proving that a committed value lies in [0, 2^n).
///
/// Uses bit decomposition with Sigma OR-proofs per bit.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RangeProof {
    /// Pedersen commitment to the value: C = v*G + r*H (compressed Ristretto, hex)
    pub value_commitment: String,
    /// Number of bits in the range proof
    pub num_bits: usize,
    /// Per-bit proofs
    pub bit_proofs: Vec<BitProof>,
    /// Context hash included in proof generation (hex)
    pub context_hash: String,
}

/// A policy compliance proof.
///
/// Proves that the transaction satisfies a policy constraint
/// (e.g., amount <= max_allowed) without revealing the policy parameters.
///
/// Implementation: Hash-based commitment to (policy_id, constraint_satisfied)
/// with a Schnorr proof of knowledge of the opening.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyProof {
    /// Policy identifier (e.g., "max_transfer", "allowed_destination")
    pub policy_id: String,
    /// Commitment to policy satisfaction (hex)
    pub commitment: String,
    /// Schnorr proof response (scalar, hex)
    pub response: String,
    /// Challenge (scalar, hex)
    pub challenge: String,
    /// Context hash (hex)
    pub context_hash: String,
}

/// A bundle of all proofs for a private transaction.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProofBundle {
    /// Proof of wallet ownership
    pub ownership_proof: OwnershipProof,
    /// Range proof for the transfer amount (optional — not all private txs need range proofs)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub range_proof: Option<RangeProof>,
    /// Policy compliance proofs
    pub policy_proofs: Vec<PolicyProof>,
    /// Binding hash tying all proofs to the transaction (hex)
    pub binding: String,
    /// Fresh nonce preventing replay (hex, 32 bytes)
    pub nonce: String,
    /// Version of the proof bundle format
    pub version: String,
}

/// Transfer envelope — the complete package transferred
/// from the online machine to the offline USB signer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransferEnvelope {
    /// Envelope format version
    pub version: String,
    /// Transaction mode
    pub mode: TransactionMode,
    /// ISO-8601 creation timestamp
    pub created_at: String,
    /// Transaction data
    pub transaction: TransactionContext,
    /// Proof bundle (only present in private mode)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub proof_bundle: Option<ProofBundle>,
    /// HMAC-SHA256 integrity tag (hex)
    pub integrity: String,
}

/// Result of proof verification on the offline signer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationResult {
    /// Whether all checks passed
    pub valid: bool,
    /// Individual check results
    pub checks: Vec<VerificationCheck>,
    /// Human-readable summary
    pub summary: String,
}

/// A single verification check result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationCheck {
    /// Name of the check
    pub name: String,
    /// Whether it passed
    pub passed: bool,
    /// Details or error message
    pub detail: String,
}

/// Human-readable transaction summary displayed before signing.
///
/// SECURITY: This is the last thing the user sees before confirming.
/// It MUST accurately reflect the transaction content.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SigningSummary {
    /// Destination address
    pub destination: String,
    /// Transfer amount in SOL
    pub amount_sol: f64,
    /// Transaction fee in SOL
    pub fee_sol: f64,
    /// Transaction mode
    pub mode: TransactionMode,
    /// Whether proof verification passed (always true for public)
    pub proof_verified: bool,
    /// Number of proofs verified (0 for public)
    pub proofs_verified_count: usize,
    /// Warnings, if any
    pub warnings: Vec<String>,
}

impl std::fmt::Display for SigningSummary {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        writeln!(f, "╔══════════════════════════════════════════════════╗")?;
        writeln!(f, "║           TRANSACTION SIGNING SUMMARY            ║")?;
        writeln!(f, "╠══════════════════════════════════════════════════╣")?;
        writeln!(f, "║ Destination: {}",  &self.destination)?;
        writeln!(f, "║ Amount:      {:.9} SOL", self.amount_sol)?;
        writeln!(f, "║ Fee:         {:.9} SOL", self.fee_sol)?;
        writeln!(f, "║ Mode:        {}", self.mode.as_str().to_uppercase())?;
        if self.mode.requires_proofs() {
            let status = if self.proof_verified { "✓ PASSED" } else { "✗ FAILED" };
            writeln!(f, "║ Proofs:      {} ({} verified)", status, self.proofs_verified_count)?;
        }
        for warning in &self.warnings {
            writeln!(f, "║ ⚠ WARNING:   {}", warning)?;
        }
        writeln!(f, "╚══════════════════════════════════════════════════╝")?;
        Ok(())
    }
}
