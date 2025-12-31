//! FFI (Foreign Function Interface) for Python integration
//!
//! This module provides C-compatible functions that can be called from Python
//! using ctypes or cffi.
//!
//! # Memory Management
//!
//! All strings returned by FFI functions are allocated by Rust and must be
//! freed by calling the corresponding `free_*` functions.
//!
//! # Thread Safety
//!
//! These functions are thread-safe and can be called from multiple threads.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

use crate::crypto::{create_encrypted_key_container, decrypt_and_sign};

/// Result code for FFI operations
#[repr(C)]
pub struct SignerResult {
    /// 0 for success, non-zero for error
    pub error_code: i32,
    /// Result string (JSON for success, error message for failure)
    /// Must be freed with free_string()
    pub result: *mut c_char,
}

impl SignerResult {
    fn success(result: String) -> Self {
        Self {
            error_code: 0,
            result: CString::new(result).unwrap_or_default().into_raw(),
        }
    }

    fn error(code: i32, message: &str) -> Self {
        Self {
            error_code: code,
            result: CString::new(message).unwrap_or_default().into_raw(),
        }
    }
}

/// Create an encrypted key container from a private key
///
/// # Arguments
/// * `private_key_b58` - Base58-encoded private key (32 or 64 bytes)
/// * `passphrase` - Null-terminated passphrase string
///
/// # Returns
/// SignerResult with JSON container on success
///
/// # Safety
/// All pointers must be valid, null-terminated C strings.
#[no_mangle]
pub unsafe extern "C" fn signer_create_container(
    private_key_b58: *const c_char,
    passphrase: *const c_char,
) -> SignerResult {
    // Validate inputs
    if private_key_b58.is_null() || passphrase.is_null() {
        return SignerResult::error(1, "Null pointer argument");
    }

    let private_key_str = match CStr::from_ptr(private_key_b58).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in private key"),
    };

    let passphrase_str = match CStr::from_ptr(passphrase).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in passphrase"),
    };

    // Decode the private key
    let private_key = match bs58::decode(private_key_str).into_vec() {
        Ok(k) => k,
        Err(e) => return SignerResult::error(3, &format!("Base58 decode error: {}", e)),
    };

    // Create container
    match create_encrypted_key_container(&private_key, passphrase_str) {
        Ok(json) => SignerResult::success(json),
        Err(e) => SignerResult::error(4, &e.to_string()),
    }
}

/// Decrypt a key container and sign a transaction
///
/// # Arguments
/// * `container_json` - Null-terminated JSON string of the encrypted container
/// * `passphrase` - Null-terminated passphrase string
/// * `transaction_b64` - Base64-encoded unsigned transaction bytes
///
/// # Returns
/// SignerResult with JSON signing result on success
///
/// # Safety
/// All pointers must be valid, null-terminated C strings.
#[no_mangle]
pub unsafe extern "C" fn signer_sign_transaction(
    container_json: *const c_char,
    passphrase: *const c_char,
    transaction_b64: *const c_char,
) -> SignerResult {
    // Validate inputs
    if container_json.is_null() || passphrase.is_null() || transaction_b64.is_null() {
        return SignerResult::error(1, "Null pointer argument");
    }

    let container_str = match CStr::from_ptr(container_json).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in container"),
    };

    let passphrase_str = match CStr::from_ptr(passphrase).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in passphrase"),
    };

    let transaction_str = match CStr::from_ptr(transaction_b64).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in transaction"),
    };

    // Decode the transaction
    let transaction_bytes =
        match base64::Engine::decode(&base64::engine::general_purpose::STANDARD, transaction_str) {
            Ok(t) => t,
            Err(e) => return SignerResult::error(3, &format!("Base64 decode error: {}", e)),
        };

    // Decrypt and sign
    match decrypt_and_sign(container_str, passphrase_str, &transaction_bytes) {
        Ok(result) => match serde_json::to_string(&result) {
            Ok(json) => SignerResult::success(json),
            Err(e) => SignerResult::error(5, &format!("Serialization error: {}", e)),
        },
        Err(e) => SignerResult::error(4, &e.to_string()),
    }
}

/// Sign a message directly with a base58-encoded private key
///
/// # Security Warning
/// This function accepts a plaintext private key. Prefer using
/// signer_sign_transaction with an encrypted container for better security.
///
/// # Arguments
/// * `private_key_b58` - Base58-encoded private key
/// * `message_b64` - Base64-encoded message to sign
///
/// # Returns
/// SignerResult with JSON signing result on success
///
/// # Safety
/// All pointers must be valid, null-terminated C strings.
#[no_mangle]
pub unsafe extern "C" fn signer_sign_direct(
    private_key_b58: *const c_char,
    message_b64: *const c_char,
) -> SignerResult {
    if private_key_b58.is_null() || message_b64.is_null() {
        return SignerResult::error(1, "Null pointer argument");
    }

    let private_key_str = match CStr::from_ptr(private_key_b58).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in private key"),
    };

    let message_str = match CStr::from_ptr(message_b64).to_str() {
        Ok(s) => s,
        Err(_) => return SignerResult::error(2, "Invalid UTF-8 in message"),
    };

    // Decode inputs
    let private_key = match bs58::decode(private_key_str).into_vec() {
        Ok(k) => k,
        Err(e) => return SignerResult::error(3, &format!("Base58 decode error: {}", e)),
    };

    let message =
        match base64::Engine::decode(&base64::engine::general_purpose::STANDARD, message_str) {
            Ok(m) => m,
            Err(e) => return SignerResult::error(3, &format!("Base64 decode error: {}", e)),
        };

    // Sign
    match crate::crypto::sign_transaction(&private_key, &message) {
        Ok(result) => match serde_json::to_string(&result) {
            Ok(json) => SignerResult::success(json),
            Err(e) => SignerResult::error(5, &format!("Serialization error: {}", e)),
        },
        Err(e) => SignerResult::error(4, &e.to_string()),
    }
}

/// Free a string allocated by Rust
///
/// # Safety
/// The pointer must have been returned by a signer_* function.
/// After calling this, the pointer is invalid.
#[no_mangle]
pub unsafe extern "C" fn signer_free_string(ptr: *mut c_char) {
    if !ptr.is_null() {
        // Convert back to CString and let it drop
        let _ = CString::from_raw(ptr);
    }
}

/// Free a SignerResult
///
/// # Safety
/// The result must have been returned by a signer_* function.
#[no_mangle]
pub unsafe extern "C" fn signer_free_result(result: SignerResult) {
    signer_free_string(result.result);
}

/// Get the library version
///
/// # Returns
/// Null-terminated version string. Do NOT free this pointer.
#[no_mangle]
pub extern "C" fn signer_version() -> *const c_char {
    static VERSION: &str = concat!(env!("CARGO_PKG_VERSION"), "\0");
    VERSION.as_ptr() as *const c_char
}

/// Check if memory locking is supported on this platform
///
/// # Returns
/// 1 if memory locking is supported, 0 otherwise
#[no_mangle]
pub extern "C" fn signer_check_mlock_support() -> i32 {
    match crate::secure_buffer::SecureBuffer::new(64) {
        Ok(buf) => {
            if buf.is_locked() {
                1
            } else {
                0
            }
        }
        Err(_) => 0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::CString;

    #[test]
    fn test_ffi_create_container() {
        // Generate a test key
        let mut seed = [0u8; 32];
        rand::RngCore::fill_bytes(&mut rand::rngs::OsRng, &mut seed);
        let key_b58 = bs58::encode(&seed).into_string();

        let key_cstr = CString::new(key_b58).unwrap();
        let pass_cstr = CString::new("test_password").unwrap();

        unsafe {
            let result = signer_create_container(key_cstr.as_ptr(), pass_cstr.as_ptr());
            assert_eq!(result.error_code, 0);
            assert!(!result.result.is_null());

            let result_str = CStr::from_ptr(result.result).to_str().unwrap();
            assert!(result_str.contains("\"version\":1"));

            signer_free_result(result);
        }
    }

    #[test]
    fn test_ffi_version() {
        let version_ptr = signer_version();
        assert!(!version_ptr.is_null());

        unsafe {
            let version = CStr::from_ptr(version_ptr).to_str().unwrap();
            assert!(!version.is_empty());
        }
    }
}
