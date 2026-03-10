//! FFI (Foreign Function Interface) for Python integration.
//!
//! Exposes the ZK proof engine to Python via C-compatible functions.
//! Uses JSON-based parameter passing for simplicity and flexibility.
//!
//! # Convention
//! - Input: JSON string (C string, null-terminated)
//! - Output: JSON string (heap-allocated, caller must free)
//! - Errors: Returned as JSON with "error" field
//!
//! # Memory Management
//! All returned strings are heap-allocated with Box::into_raw.
//! The caller must free them with `coldstar_zk_free_string`.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

use serde::{Deserialize, Serialize};

use crate::envelope;
use crate::policy::PolicyEngine;
use crate::proofs::{ownership, range};
use crate::types::*;

/// FFI response wrapper
#[derive(Serialize)]
struct FfiResponse {
    success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

impl FfiResponse {
    fn ok(data: serde_json::Value) -> Self {
        FfiResponse {
            success: true,
            data: Some(data),
            error: None,
        }
    }

    fn err(msg: String) -> Self {
        FfiResponse {
            success: false,
            data: None,
            error: Some(msg),
        }
    }

    fn to_c_string(self) -> *mut c_char {
        let json = serde_json::to_string(&self).unwrap_or_else(|_| {
            r#"{"success":false,"error":"Failed to serialize response"}"#.to_string()
        });
        CString::new(json)
            .unwrap_or_else(|_| CString::new("null").unwrap())
            .into_raw()
    }
}

/// Helper to parse a C string to a Rust &str
unsafe fn parse_c_str<'a>(ptr: *const c_char) -> Result<&'a str, String> {
    if ptr.is_null() {
        return Err("Null pointer".to_string());
    }
    CStr::from_ptr(ptr)
        .to_str()
        .map_err(|e| format!("Invalid UTF-8: {}", e))
}

// ============================================================================
// FFI Functions
// ============================================================================

/// Generate an ownership proof.
///
/// Input JSON:
/// ```json
/// {
///   "secret_key_hex": "...",    // 32-byte secret key, hex-encoded
///   "context_data_hex": "..."   // context data, hex-encoded
/// }
/// ```
///
/// Output JSON:
/// ```json
/// {
///   "success": true,
///   "data": { "ownership_proof": { ... } }
/// }
/// ```
#[no_mangle]
pub unsafe extern "C" fn coldstar_zk_prove_ownership(input_json: *const c_char) -> *mut c_char {
    let input = match parse_c_str(input_json) {
        Ok(s) => s,
        Err(e) => return FfiResponse::err(e).to_c_string(),
    };

    #[derive(Deserialize)]
    struct Input {
        secret_key_hex: String,
        context_data_hex: String,
    }

    let params: Input = match serde_json::from_str(input) {
        Ok(p) => p,
        Err(e) => return FfiResponse::err(format!("Invalid input: {}", e)).to_c_string(),
    };

    let secret_key = match hex::decode(&params.secret_key_hex) {
        Ok(k) if k.len() == 32 => {
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&k);
            arr
        }
        Ok(k) => {
            return FfiResponse::err(format!("Secret key must be 32 bytes, got {}", k.len()))
                .to_c_string()
        }
        Err(e) => return FfiResponse::err(format!("Invalid hex: {}", e)).to_c_string(),
    };

    let context_data = match hex::decode(&params.context_data_hex) {
        Ok(d) => d,
        Err(e) => return FfiResponse::err(format!("Invalid context hex: {}", e)).to_c_string(),
    };

    match ownership::prove_ownership(&secret_key, &context_data) {
        Ok(proof) => {
            let data = serde_json::to_value(&proof).unwrap();
            FfiResponse::ok(serde_json::json!({ "ownership_proof": data })).to_c_string()
        }
        Err(e) => FfiResponse::err(format!("Proof generation failed: {}", e)).to_c_string(),
    }
}

/// Verify an ownership proof.
///
/// Input JSON:
/// ```json
/// {
///   "proof": { ... },           // OwnershipProof
///   "context_data_hex": "..."   // context data, hex-encoded
/// }
/// ```
#[no_mangle]
pub unsafe extern "C" fn coldstar_zk_verify_ownership(input_json: *const c_char) -> *mut c_char {
    let input = match parse_c_str(input_json) {
        Ok(s) => s,
        Err(e) => return FfiResponse::err(e).to_c_string(),
    };

    #[derive(Deserialize)]
    struct Input {
        proof: OwnershipProof,
        context_data_hex: String,
    }

    let params: Input = match serde_json::from_str(input) {
        Ok(p) => p,
        Err(e) => return FfiResponse::err(format!("Invalid input: {}", e)).to_c_string(),
    };

    let context_data = match hex::decode(&params.context_data_hex) {
        Ok(d) => d,
        Err(e) => return FfiResponse::err(format!("Invalid context hex: {}", e)).to_c_string(),
    };

    match ownership::verify_ownership(&params.proof, &context_data) {
        Ok(()) => FfiResponse::ok(serde_json::json!({ "valid": true })).to_c_string(),
        Err(e) => FfiResponse::ok(serde_json::json!({
            "valid": false,
            "error": format!("{}", e)
        }))
        .to_c_string(),
    }
}

/// Generate a range proof.
///
/// Input JSON:
/// ```json
/// {
///   "value": 1000000000,
///   "num_bits": 64,
///   "context_data_hex": "..."
/// }
/// ```
#[no_mangle]
pub unsafe extern "C" fn coldstar_zk_prove_range(input_json: *const c_char) -> *mut c_char {
    let input = match parse_c_str(input_json) {
        Ok(s) => s,
        Err(e) => return FfiResponse::err(e).to_c_string(),
    };

    #[derive(Deserialize)]
    struct Input {
        value: u64,
        num_bits: usize,
        context_data_hex: String,
    }

    let params: Input = match serde_json::from_str(input) {
        Ok(p) => p,
        Err(e) => return FfiResponse::err(format!("Invalid input: {}", e)).to_c_string(),
    };

    let context_data = match hex::decode(&params.context_data_hex) {
        Ok(d) => d,
        Err(e) => return FfiResponse::err(format!("Invalid context hex: {}", e)).to_c_string(),
    };

    match range::prove_range(params.value, params.num_bits, &context_data) {
        Ok((proof, _blinding)) => {
            let data = serde_json::to_value(&proof).unwrap();
            FfiResponse::ok(serde_json::json!({ "range_proof": data })).to_c_string()
        }
        Err(e) => FfiResponse::err(format!("Range proof failed: {}", e)).to_c_string(),
    }
}

/// Verify a range proof.
///
/// Input JSON:
/// ```json
/// {
///   "proof": { ... },           // RangeProof
///   "context_data_hex": "..."
/// }
/// ```
#[no_mangle]
pub unsafe extern "C" fn coldstar_zk_verify_range(input_json: *const c_char) -> *mut c_char {
    let input = match parse_c_str(input_json) {
        Ok(s) => s,
        Err(e) => return FfiResponse::err(e).to_c_string(),
    };

    #[derive(Deserialize)]
    struct Input {
        proof: RangeProof,
        context_data_hex: String,
    }

    let params: Input = match serde_json::from_str(input) {
        Ok(p) => p,
        Err(e) => return FfiResponse::err(format!("Invalid input: {}", e)).to_c_string(),
    };

    let context_data = match hex::decode(&params.context_data_hex) {
        Ok(d) => d,
        Err(e) => return FfiResponse::err(format!("Invalid context hex: {}", e)).to_c_string(),
    };

    match range::verify_range(&params.proof, &context_data) {
        Ok(()) => FfiResponse::ok(serde_json::json!({ "valid": true })).to_c_string(),
        Err(e) => FfiResponse::ok(serde_json::json!({
            "valid": false,
            "error": format!("{}", e)
        }))
        .to_c_string(),
    }
}

/// Build and verify a complete transfer envelope.
///
/// Input JSON:
/// ```json
/// {
///   "envelope_json": "..."  // Serialized TransferEnvelope  
/// }
/// ```
#[no_mangle]
pub unsafe extern "C" fn coldstar_zk_validate_envelope(input_json: *const c_char) -> *mut c_char {
    let input = match parse_c_str(input_json) {
        Ok(s) => s,
        Err(e) => return FfiResponse::err(e).to_c_string(),
    };

    #[derive(Deserialize)]
    struct Input {
        envelope_json: String,
    }

    let params: Input = match serde_json::from_str(input) {
        Ok(p) => p,
        Err(e) => return FfiResponse::err(format!("Invalid input: {}", e)).to_c_string(),
    };

    let env = match envelope::deserialize_envelope(&params.envelope_json) {
        Ok(e) => e,
        Err(e) => {
            return FfiResponse::err(format!("Invalid envelope: {}", e)).to_c_string()
        }
    };

    let mut engine = PolicyEngine::new();
    match engine.validate_envelope(&env) {
        Ok((result, summary)) => {
            let data = serde_json::json!({
                "verification": serde_json::to_value(&result).unwrap(),
                "summary": serde_json::to_value(&summary).unwrap(),
            });
            FfiResponse::ok(data).to_c_string()
        }
        Err(e) => FfiResponse::err(format!("Validation failed: {}", e)).to_c_string(),
    }
}

/// Get the library version.
#[no_mangle]
pub extern "C" fn coldstar_zk_version() -> *mut c_char {
    let version = format!(
        "{{\"version\":\"{}\",\"name\":\"coldstar_zk\"}}",
        crate::VERSION
    );
    CString::new(version).unwrap().into_raw()
}

/// Free a string returned by any coldstar_zk function.
///
/// # Safety
/// The pointer must have been returned by a coldstar_zk function.
#[no_mangle]
pub unsafe extern "C" fn coldstar_zk_free_string(ptr: *mut c_char) {
    if !ptr.is_null() {
        drop(CString::from_raw(ptr));
    }
}
