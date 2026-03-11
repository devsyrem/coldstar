//! FFI exports for ZK proof operations
//!
//! Provides C-compatible functions for Python integration of ZK proofs.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

use crate::ffi::SignerResult;
use crate::zk_proofs::{
    ConfidentialTransferProofBundle, ElGamalCiphertext, ElGamalKeypair, OwnershipProof,
};

use base64::Engine;
use curve25519_dalek::ristretto::CompressedRistretto;

/// Generate an ElGamal keypair, optionally derived from an Ed25519 seed.
///
/// # Arguments
/// * `ed25519_seed_b58` - Base58-encoded 32-byte Ed25519 seed, or null for random
///
/// # Returns
/// JSON: {"public_key": "<base64>", "public_key_hex": "<hex>"}
#[no_mangle]
pub unsafe extern "C" fn zk_generate_elgamal_keypair(
    ed25519_seed_b58: *const c_char,
) -> SignerResult {
    let keypair = if ed25519_seed_b58.is_null() {
        ElGamalKeypair::generate()
    } else {
        let seed_str = match CStr::from_ptr(ed25519_seed_b58).to_str() {
            Ok(s) => s,
            Err(_) => return SignerResult::error(2, "Invalid UTF-8"),
        };
        let seed_bytes = match bs58::decode(seed_str).into_vec() {
            Ok(b) => b,
            Err(e) => return SignerResult::error(3, &format!("Base58 error: {}", e)),
        };
        if seed_bytes.len() < 32 {
            return SignerResult::error(3, "Seed must be at least 32 bytes");
        }
        let mut seed = [0u8; 32];
        seed.copy_from_slice(&seed_bytes[..32]);
        ElGamalKeypair::from_ed25519_seed(&seed)
    };

    let result = serde_json::json!({
        "public_key": base64::engine::general_purpose::STANDARD.encode(keypair.public_key_bytes()),
        "public_key_hex": hex::encode(keypair.public_key_bytes()),
    });

    SignerResult::success(result.to_string())
}

/// Encrypt an amount using ElGamal encryption.
///
/// # Arguments
/// * `amount` - The amount to encrypt (u64)
/// * `public_key_b64` - Base64-encoded ElGamal public key (32 bytes)
///
/// # Returns
/// JSON with ciphertext data
#[no_mangle]
pub unsafe extern "C" fn zk_encrypt_amount(
    amount: u64,
    public_key_b64: *const c_char,
) -> SignerResult {
    if public_key_b64.is_null() {
        return SignerResult::error(1, "Null public key");
    }

    let pk_str = match CStr::from_ptr(public_key_b64).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8"),
    };

    let pk_bytes = match base64::engine::general_purpose::STANDARD.decode(pk_str) {
        Ok(b) => b,
        Err(e) => return SignerResult::error(3, &format!("Base64 error: {}", e)),
    };

    if pk_bytes.len() != 32 {
        return SignerResult::error(3, "Public key must be 32 bytes");
    }

    let compressed = match CompressedRistretto::from_slice(&pk_bytes) {
        Ok(c) => c,
        Err(_) => return SignerResult::error(3, "Invalid compressed point"),
    };
    let pubkey = match compressed.decompress() {
        Some(p) => p,
        None => return SignerResult::error(3, "Failed to decompress public key"),
    };

    let (ct, _randomness) = ElGamalCiphertext::encrypt(amount, &pubkey);

    let result = serde_json::json!({
        "ciphertext_b64": base64::engine::general_purpose::STANDARD.encode(ct.to_bytes()),
        "commitment_b64": base64::engine::general_purpose::STANDARD.encode(ct.commitment),
        "handle_b64": base64::engine::general_purpose::STANDARD.encode(ct.handle),
    });

    SignerResult::success(result.to_string())
}

/// Generate a complete confidential transfer proof bundle.
///
/// # Arguments
/// * `amount` - The amount to transfer
/// * `sender_seed_b58` - Sender's Ed25519 seed (Base58)
/// * `recipient_pubkey_b64` - Recipient's ElGamal public key (Base64, 32 bytes)
/// * `auditor_pubkey_b64` - Optional auditor key (Base64, 32 bytes, or null)
///
/// # Returns
/// JSON proof bundle with all ciphertexts and proofs
#[no_mangle]
pub unsafe extern "C" fn zk_generate_transfer_proof(
    amount: u64,
    sender_seed_b58: *const c_char,
    recipient_pubkey_b64: *const c_char,
    auditor_pubkey_b64: *const c_char,
) -> SignerResult {
    if sender_seed_b58.is_null() || recipient_pubkey_b64.is_null() {
        return SignerResult::error(1, "Null argument");
    }

    // Parse sender seed
    let seed_str = match CStr::from_ptr(sender_seed_b58).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in sender seed"),
    };
    let seed_bytes = match bs58::decode(seed_str).into_vec() {
        Ok(b) => b,
        Err(e) => return SignerResult::error(3, &format!("Sender seed decode: {}", e)),
    };
    if seed_bytes.len() < 32 {
        return SignerResult::error(3, "Sender seed must be >= 32 bytes");
    }
    let mut seed = [0u8; 32];
    seed.copy_from_slice(&seed_bytes[..32]);
    let sender_keypair = ElGamalKeypair::from_ed25519_seed(&seed);

    // Parse recipient public key
    let rpk_str = match CStr::from_ptr(recipient_pubkey_b64).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in recipient key"),
    };
    let rpk_bytes = match base64::engine::general_purpose::STANDARD.decode(rpk_str) {
        Ok(b) => b,
        Err(e) => return SignerResult::error(3, &format!("Recipient key decode: {}", e)),
    };
    if rpk_bytes.len() != 32 {
        return SignerResult::error(3, "Recipient key must be 32 bytes");
    }
    let rpk_compressed = match CompressedRistretto::from_slice(&rpk_bytes) {
        Ok(c) => c,
        Err(_) => return SignerResult::error(3, "Invalid recipient point"),
    };
    let recipient_pubkey = match rpk_compressed.decompress() {
        Some(p) => p,
        None => return SignerResult::error(3, "Failed to decompress recipient key"),
    };

    // Parse optional auditor key
    let auditor_pubkey = if !auditor_pubkey_b64.is_null() {
        let apk_str = match CStr::from_ptr(auditor_pubkey_b64).to_str() {
            Ok(s) => s,
            Err(_) => return SignerResult::error(2, "Invalid UTF-8 in auditor key"),
        };
        let apk_bytes = match base64::engine::general_purpose::STANDARD.decode(apk_str) {
            Ok(b) => b,
            Err(e) => return SignerResult::error(3, &format!("Auditor key decode: {}", e)),
        };
        if apk_bytes.len() != 32 {
            return SignerResult::error(3, "Auditor key must be 32 bytes");
        }
        match CompressedRistretto::from_slice(&apk_bytes) {
            Ok(c) => c.decompress(),
            Err(_) => None,
        }
    } else {
        None
    };

    // Generate the proof bundle
    let bundle = match ConfidentialTransferProofBundle::generate(
        amount,
        &sender_keypair,
        &recipient_pubkey,
        auditor_pubkey.as_ref(),
    ) {
        Ok(b) => b,
        Err(e) => return SignerResult::error(4, &e.to_string()),
    };

    match bundle.to_json() {
        Ok(json) => {
            let result = serde_json::json!({
                "status": "success",
                "sender_elgamal_pubkey": base64::engine::general_purpose::STANDARD.encode(
                    sender_keypair.public_key_bytes()
                ),
                "proof_bundle": serde_json::from_str::<serde_json::Value>(&json).unwrap_or_default(),
                "compact_proof_size": bundle.to_compact_bytes().len(),
                "compact_proof_b64": base64::engine::general_purpose::STANDARD.encode(
                    bundle.to_compact_bytes()
                ),
            });
            SignerResult::success(result.to_string())
        }
        Err(e) => SignerResult::error(5, &e.to_string()),
    }
}

/// Verify a confidential transfer proof bundle.
///
/// # Arguments
/// * `proof_json` - JSON-encoded proof bundle
/// * `sender_pubkey_b64` - Sender's ElGamal public key (Base64, 32 bytes)
///
/// # Returns
/// JSON: {"valid": true/false, "checks": {...}}
#[no_mangle]
pub unsafe extern "C" fn zk_verify_transfer_proof(
    proof_json: *const c_char,
    sender_pubkey_b64: *const c_char,
) -> SignerResult {
    if proof_json.is_null() || sender_pubkey_b64.is_null() {
        return SignerResult::error(1, "Null argument");
    }

    let json_str = match CStr::from_ptr(proof_json).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8"),
    };

    let pk_str = match CStr::from_ptr(sender_pubkey_b64).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8"),
    };

    let pk_bytes = match base64::engine::general_purpose::STANDARD.decode(pk_str) {
        Ok(b) => b,
        Err(e) => return SignerResult::error(3, &format!("Key decode: {}", e)),
    };

    if pk_bytes.len() != 32 {
        return SignerResult::error(3, "Public key must be 32 bytes");
    }

    let mut pubkey_arr = [0u8; 32];
    pubkey_arr.copy_from_slice(&pk_bytes);

    let bundle = match ConfidentialTransferProofBundle::from_json(json_str) {
        Ok(b) => b,
        Err(e) => return SignerResult::error(4, &format!("Parse error: {}", e)),
    };

    let ownership_valid = bundle.ownership_proof.verify(&pubkey_arr);
    let range_valid = bundle
        .range_proof
        .verify(&bundle.source_ciphertext.commitment);
    let validity_valid = bundle
        .validity_proof
        .verify(&bundle.source_ciphertext, &pubkey_arr);
    let all_valid = ownership_valid && range_valid && validity_valid;

    let result = serde_json::json!({
        "valid": all_valid,
        "checks": {
            "ownership_proof": ownership_valid,
            "range_proof": range_valid,
            "validity_proof": validity_valid,
        }
    });

    SignerResult::success(result.to_string())
}

/// Generate an ownership proof for an ElGamal keypair.
#[no_mangle]
pub unsafe extern "C" fn zk_prove_ownership(
    ed25519_seed_b58: *const c_char,
) -> SignerResult {
    if ed25519_seed_b58.is_null() {
        return SignerResult::error(1, "Null seed");
    }

    let seed_str = match CStr::from_ptr(ed25519_seed_b58).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8"),
    };

    let seed_bytes = match bs58::decode(seed_str).into_vec() {
        Ok(b) => b,
        Err(e) => return SignerResult::error(3, &format!("Decode: {}", e)),
    };

    if seed_bytes.len() < 32 {
        return SignerResult::error(3, "Seed too short");
    }

    let mut seed = [0u8; 32];
    seed.copy_from_slice(&seed_bytes[..32]);
    let keypair = ElGamalKeypair::from_ed25519_seed(&seed);
    let proof = OwnershipProof::prove(&keypair);

    let result = serde_json::json!({
        "public_key": base64::engine::general_purpose::STANDARD.encode(
            keypair.public_key_bytes()
        ),
        "proof": base64::engine::general_purpose::STANDARD.encode(proof.to_bytes()),
        "valid": proof.verify(&keypair.public_key_bytes()),
    });

    SignerResult::success(result.to_string())
}

/// Get ZK module version info
#[no_mangle]
pub extern "C" fn zk_version() -> SignerResult {
    let result = serde_json::json!({
        "version": "1.0.0",
        "module": "coldstar-zk-proofs",
        "features": [
            "elgamal_encryption",
            "range_proofs",
            "ownership_proofs",
            "equality_proofs",
            "validity_proofs",
            "confidential_transfer_bundles"
        ],
        "curve": "ristretto255",
        "transcript": "merlin"
    });

    SignerResult::success(result.to_string())
}
