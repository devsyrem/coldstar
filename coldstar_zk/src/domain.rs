//! Domain separation constants for the Coldstar ZK system.
//!
//! Domain separation ensures that proofs, commitments, and hashes
//! created in one context cannot be reused in another context.
//! Every hash computation includes a domain tag as the first input.
//!
//! # SECURITY: Adding a new domain tag
//! When adding a new proof type or hash context, ALWAYS add a unique
//! domain tag here. Never reuse tags across different proof types.

/// Domain tag for Schnorr NIZK ownership proofs
pub const DOMAIN_OWNERSHIP_PROOF: &[u8] = b"coldstar.zk.ownership.v1";

/// Domain tag for range proof bit commitments
pub const DOMAIN_RANGE_PROOF: &[u8] = b"coldstar.zk.range.v1";

/// Domain tag for range proof OR-proof challenges
pub const DOMAIN_RANGE_OR_PROOF: &[u8] = b"coldstar.zk.range.or.v1";

/// Domain tag for policy compliance proofs
pub const DOMAIN_POLICY_PROOF: &[u8] = b"coldstar.zk.policy.v1";

/// Domain tag for Pedersen commitment blinding factor generation
pub const DOMAIN_COMMITMENT: &[u8] = b"coldstar.zk.commitment.v1";

/// Domain tag for proof-to-transaction binding
pub const DOMAIN_BINDING: &[u8] = b"coldstar.zk.binding.v1";

/// Domain tag for envelope HMAC integrity
pub const DOMAIN_ENVELOPE_HMAC: &[u8] = b"coldstar.zk.envelope.hmac.v1";

/// Domain tag for the secondary generator point H
/// H = hash_to_point(DOMAIN_GENERATOR_H) — nothing-up-my-sleeve construction
pub const DOMAIN_GENERATOR_H: &[u8] = b"coldstar.zk.generator.H.v1";

/// Domain tag for nonce generation
pub const DOMAIN_NONCE: &[u8] = b"coldstar.zk.nonce.v1";

/// Domain tag for transaction context hashing
pub const DOMAIN_TX_CONTEXT: &[u8] = b"coldstar.zk.tx.context.v1";

/// Maximum allowed bit width for range proofs.
/// 64 bits covers the full u64 range (sufficient for Solana lamports).
pub const MAX_RANGE_BITS: usize = 64;

/// Default bit width for range proofs (covers amounts up to ~18.4 SOL in lamports)
pub const DEFAULT_RANGE_BITS: usize = 64;
