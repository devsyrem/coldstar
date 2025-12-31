//! Secure memory buffer implementation
//!
//! This module provides a memory-locked buffer that:
//! - Locks memory to prevent swapping (mlock)
//! - Automatically zeroizes on drop
//! - Handles panic-safe cleanup
//! - Prevents copies of sensitive data

use std::ops::{Deref, DerefMut};
use std::ptr;
use zeroize::Zeroize;

use crate::error::SignerError;

/// A secure buffer that locks its memory and zeroizes on drop
///
/// # Memory Lifecycle
///
/// 1. Allocation: Buffer is allocated with specified capacity
/// 2. Locking: Memory is locked via mlock() to prevent swapping
/// 3. Usage: Data can be written/read within the locked region
/// 4. Cleanup: On drop (normal or panic), memory is:
///    - Zeroized (overwritten with zeros)
///    - Unlocked (munlock)
///    - Deallocated
///
/// # Security Properties
///
/// - Memory is never swapped to disk
/// - Contents are zeroized even on panic (via Drop)
/// - No implicit copies are made
/// - Debug output does not reveal contents
pub struct SecureBuffer {
    /// The underlying data buffer
    data: Vec<u8>,
    /// Whether memory is currently locked
    is_locked: bool,
}

/// Configuration for memory locking behavior
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum LockingMode {
    /// Require memory locking - fail if mlock is not available
    Strict,
    /// Allow fallback if mlock fails (less secure, logs warning)
    Permissive,
}

impl SecureBuffer {
    /// Create a new secure buffer with strict memory locking.
    ///
    /// This is the recommended constructor for security-critical operations.
    /// It will fail if memory cannot be locked.
    ///
    /// # Arguments
    /// * `capacity` - The size in bytes to allocate
    ///
    /// # Returns
    /// * `Ok(SecureBuffer)` - A locked buffer
    /// * `Err(SignerError::MemoryLockFailed)` - If memory locking fails
    ///
    /// # Memory Lifecycle Note
    /// The buffer is zeroed on allocation and will be locked immediately.
    pub fn new(capacity: usize) -> Result<Self, SignerError> {
        Self::with_mode(capacity, LockingMode::Strict)
    }

    /// Create a new secure buffer with configurable locking mode.
    ///
    /// # Arguments
    /// * `capacity` - The size in bytes to allocate
    /// * `mode` - Whether to require strict memory locking
    ///
    /// # Returns
    /// * `Ok(SecureBuffer)` - A buffer (locked if possible)
    /// * `Err(SignerError)` - If strict mode and locking fails
    pub fn with_mode(capacity: usize, mode: LockingMode) -> Result<Self, SignerError> {
        let data = vec![0u8; capacity];

        // Lock the memory to prevent swapping
        let locked = lock_memory(&data);

        if mode == LockingMode::Strict && !locked {
            return Err(SignerError::MemoryLockFailed(
                "mlock failed - memory may be swapped to disk. \
                 Check ulimit -l or run with CAP_IPC_LOCK capability.".to_string()
            ));
        }

        if !locked {
            eprintln!(
                "Warning: Memory locking failed. Private keys may be swapped to disk. \
                 Consider running with elevated privileges or increasing ulimit -l."
            );
        }

        Ok(Self {
            data,
            is_locked: locked,
        })
    }

    /// Create a new secure buffer with permissive mode (for testing/development).
    ///
    /// This allows the buffer to work even if mlock fails, but logs a warning.
    /// NOT recommended for production use with real private keys.
    pub fn new_permissive(capacity: usize) -> Result<Self, SignerError> {
        Self::with_mode(capacity, LockingMode::Permissive)
    }

    /// Create a secure buffer from existing data with strict locking.
    ///
    /// The source data is copied into locked memory and the original
    /// is NOT zeroized (caller's responsibility).
    ///
    /// # Memory Lifecycle Note
    /// The caller should zeroize any source data after calling this.
    pub fn from_slice(source: &[u8]) -> Result<Self, SignerError> {
        Self::from_slice_with_mode(source, LockingMode::Strict)
    }

    /// Create a secure buffer from existing data with configurable locking.
    pub fn from_slice_with_mode(source: &[u8], mode: LockingMode) -> Result<Self, SignerError> {
        let mut buffer = Self::with_mode(source.len(), mode)?;
        buffer.data.copy_from_slice(source);
        Ok(buffer)
    }

    /// Create a secure buffer from existing data with permissive locking.
    pub fn from_slice_permissive(source: &[u8]) -> Result<Self, SignerError> {
        Self::from_slice_with_mode(source, LockingMode::Permissive)
    }

    /// Get the length of the buffer
    pub fn len(&self) -> usize {
        self.data.len()
    }

    /// Check if the buffer is empty
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    /// Check if memory is locked
    pub fn is_locked(&self) -> bool {
        self.is_locked
    }

    /// Get a reference to the underlying data
    ///
    /// # Security Note
    /// The returned reference is only valid within the current scope.
    /// Do not store or copy the referenced data.
    pub fn as_slice(&self) -> &[u8] {
        &self.data
    }

    /// Get a mutable reference to the underlying data
    ///
    /// # Security Note
    /// Modifications should be done carefully. After use,
    /// call zeroize() explicitly if needed before the natural drop.
    pub fn as_mut_slice(&mut self) -> &mut [u8] {
        &mut self.data
    }

    /// Explicitly zeroize the buffer contents
    ///
    /// This is also called automatically on drop.
    pub fn zeroize(&mut self) {
        self.data.zeroize();
    }

    /// Resize the buffer (maintains strict locking requirement)
    ///
    /// Note: This may cause reallocation. The old memory is zeroized
    /// before being freed. If memory locking fails on the new buffer,
    /// an error is returned and the original buffer is preserved.
    pub fn resize(&mut self, new_len: usize) -> Result<(), SignerError> {
        self.resize_with_mode(new_len, LockingMode::Strict)
    }

    /// Resize the buffer with configurable locking mode
    pub fn resize_with_mode(&mut self, new_len: usize, mode: LockingMode) -> Result<(), SignerError> {
        if new_len > self.data.len() {
            // Create new buffer first
            let mut new_data = vec![0u8; new_len];
            
            // Lock new memory before proceeding
            let new_locked = lock_memory(&new_data);
            
            if mode == LockingMode::Strict && !new_locked {
                // Don't proceed - original buffer is preserved
                return Err(SignerError::MemoryLockFailed(
                    "mlock failed on resized buffer".to_string()
                ));
            }

            // Unlock old memory
            if self.is_locked {
                unlock_memory(&self.data);
            }

            // Copy data and zeroize old
            new_data[..self.data.len()].copy_from_slice(&self.data);
            self.data.zeroize();

            self.is_locked = new_locked;
            self.data = new_data;
        } else {
            // Shrinking: just truncate and zeroize the rest
            for byte in &mut self.data[new_len..] {
                *byte = 0;
            }
            self.data.truncate(new_len);
        }

        Ok(())
    }
}

impl Drop for SecureBuffer {
    fn drop(&mut self) {
        // CRITICAL: Zeroize memory before releasing
        // This happens even on panic due to Drop semantics
        self.data.zeroize();

        // Unlock the memory
        if self.is_locked {
            unlock_memory(&self.data);
        }

        // Memory will be freed by Vec's Drop
    }
}

impl Deref for SecureBuffer {
    type Target = [u8];

    fn deref(&self) -> &Self::Target {
        &self.data
    }
}

impl DerefMut for SecureBuffer {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.data
    }
}

// Prevent accidental debug printing of sensitive data
impl std::fmt::Debug for SecureBuffer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SecureBuffer")
            .field("len", &self.data.len())
            .field("is_locked", &self.is_locked)
            .field("data", &"[REDACTED]")
            .finish()
    }
}

/// Lock memory to prevent swapping (platform-specific)
#[cfg(unix)]
fn lock_memory(data: &[u8]) -> bool {
    use std::ffi::c_void;

    if data.is_empty() {
        return true;
    }

    unsafe {
        let ptr = data.as_ptr() as *const c_void;
        let len = data.len();

        // mlock() locks the memory region containing the specified address range
        libc::mlock(ptr, len) == 0
    }
}

#[cfg(unix)]
fn unlock_memory(data: &[u8]) {
    use std::ffi::c_void;

    if data.is_empty() {
        return;
    }

    unsafe {
        let ptr = data.as_ptr() as *const c_void;
        let len = data.len();
        libc::munlock(ptr, len);
    }
}

#[cfg(windows)]
fn lock_memory(data: &[u8]) -> bool {
    if data.is_empty() {
        return true;
    }

    unsafe {
        use std::ffi::c_void;
        extern "system" {
            fn VirtualLock(lpAddress: *const c_void, dwSize: usize) -> i32;
        }

        VirtualLock(data.as_ptr() as *const c_void, data.len()) != 0
    }
}

#[cfg(windows)]
fn unlock_memory(data: &[u8]) {
    if data.is_empty() {
        return;
    }

    unsafe {
        use std::ffi::c_void;
        extern "system" {
            fn VirtualUnlock(lpAddress: *const c_void, dwSize: usize) -> i32;
        }

        VirtualUnlock(data.as_ptr() as *const c_void, data.len());
    }
}

#[cfg(not(any(unix, windows)))]
fn lock_memory(_data: &[u8]) -> bool {
    // Platform doesn't support memory locking
    // Continue anyway but log a warning
    eprintln!("Warning: Memory locking not supported on this platform");
    false
}

#[cfg(not(any(unix, windows)))]
fn unlock_memory(_data: &[u8]) {
    // No-op on unsupported platforms
}

/// A guard that holds a secure reference and zeroizes on drop
///
/// Useful for temporary access to sensitive data within a scope.
pub struct SecureGuard<'a> {
    data: &'a mut [u8],
}

impl<'a> SecureGuard<'a> {
    /// Create a new guard for the given mutable slice
    pub fn new(data: &'a mut [u8]) -> Self {
        Self { data }
    }
}

impl<'a> Deref for SecureGuard<'a> {
    type Target = [u8];

    fn deref(&self) -> &Self::Target {
        self.data
    }
}

impl<'a> DerefMut for SecureGuard<'a> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.data
    }
}

impl<'a> Drop for SecureGuard<'a> {
    fn drop(&mut self) {
        // Zeroize on drop
        for byte in self.data.iter_mut() {
            unsafe {
                ptr::write_volatile(byte, 0);
            }
        }
        std::sync::atomic::compiler_fence(std::sync::atomic::Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_secure_buffer_creation_permissive() {
        // Use permissive mode for tests (mlock may not be available)
        let buffer = SecureBuffer::new_permissive(32).unwrap();
        assert_eq!(buffer.len(), 32);
        assert!(buffer.as_slice().iter().all(|&b| b == 0));
    }

    #[test]
    fn test_secure_buffer_from_slice_permissive() {
        let data = [1u8, 2, 3, 4, 5];
        let buffer = SecureBuffer::from_slice_permissive(&data).unwrap();
        assert_eq!(buffer.as_slice(), &data);
    }

    #[test]
    fn test_secure_buffer_zeroize() {
        let mut buffer = SecureBuffer::from_slice_permissive(&[1, 2, 3, 4]).unwrap();
        buffer.zeroize();
        assert!(buffer.as_slice().iter().all(|&b| b == 0));
    }

    #[test]
    fn test_debug_redacts_data() {
        let buffer = SecureBuffer::from_slice_permissive(&[0xDE, 0xAD, 0xBE, 0xEF]).unwrap();
        let debug_str = format!("{:?}", buffer);
        assert!(debug_str.contains("[REDACTED]"));
        assert!(!debug_str.contains("DEAD"));
        assert!(!debug_str.contains("BEEF"));
    }

    #[test]
    fn test_strict_mode_checks_locking() {
        // This test verifies that strict mode properly checks locking
        // On systems without mlock, this will fail; on systems with mlock, it will succeed
        let result = SecureBuffer::new(32);
        // Either it works (locked) or fails (strict mode detected no lock)
        match result {
            Ok(buf) => assert!(buf.is_locked(), "Strict mode should only succeed if locked"),
            Err(SignerError::MemoryLockFailed(_)) => {
                // Expected on systems without mlock
            }
            Err(e) => panic!("Unexpected error: {}", e),
        }
    }
}
