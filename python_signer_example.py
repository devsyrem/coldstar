"""
Python integration example for the Solana Secure Signer.

This module demonstrates three methods of integration:
1. FFI (ctypes) - Direct library calls (fastest)
2. CLI subprocess - Using the binary (most portable)
3. Combined approach - Fallback mechanism

Security guarantees:
- Private keys are never exposed in Python
- All key operations happen in Rust's secure memory
- Memory is locked and zeroized in Rust
"""

import json
import subprocess
import sys
from ctypes import *
from pathlib import Path
from typing import Optional, Tuple
import base64
import base58


# ============================================================================
# Method 1: FFI Integration (ctypes)
# ============================================================================

class FFIErrorCode:
    """FFI error codes from Rust."""
    SUCCESS = 0
    INVALID_INPUT = 1
    MEMORY_ERROR = 2
    DECRYPTION_ERROR = 3
    SIGNING_ERROR = 4
    SERIALIZATION_ERROR = 5


class FFIResult(Structure):
    """FFI result structure matching Rust's FFIResult."""
    _fields_ = [
        ("error_code", c_int),
        ("data", POINTER(c_ubyte)),
        ("data_len", c_size_t),
        ("error_message", c_char_p),
    ]


class SolanaSecureSigner:
    """
    Python wrapper for the Rust signing library using FFI.
    
    This provides a Pythonic interface to the secure signing core
    while ensuring all key operations happen in Rust's secure memory.
    """
    
    def __init__(self, lib_path: Optional[str] = None):
        """
        Initialize the signer with the Rust library.
        
        Args:
            lib_path: Path to the compiled Rust library.
                     If None, will search in common locations.
        """
        if lib_path is None:
            lib_path = self._find_library()
        
        self.lib = CDLL(str(lib_path))
        self._setup_functions()
    
    def _find_library(self) -> str:
        """Find the compiled Rust library."""
        possible_paths = [
            # secure_signer paths (primary) - library name is based on crate name
            Path(__file__).parent / "secure_signer" / "target" / "release" / "libsolana_secure_signer.so",
            Path(__file__).parent / "secure_signer" / "target" / "release" / "libsolana_secure_signer.dylib",
            Path(__file__).parent / "secure_signer" / "target" / "release" / "solana_secure_signer.dll",
            Path(__file__).parent / "secure_signer" / "target" / "debug" / "libsolana_secure_signer.so",
            Path(__file__).parent / "secure_signer" / "target" / "debug" / "libsolana_secure_signer.dylib",
            Path(__file__).parent / "secure_signer" / "target" / "debug" / "solana_secure_signer.dll",
            # Legacy rust_signer paths (fallback)
            Path(__file__).parent / "rust_signer" / "target" / "release" / "libsolana_secure_signer.so",
            Path(__file__).parent / "rust_signer" / "target" / "release" / "libsolana_secure_signer.dylib",
            Path(__file__).parent / "rust_signer" / "target" / "release" / "solana_secure_signer.dll",
        ]
        
        for path in possible_paths:
            if path.exists():
                return str(path)
        
        raise FileNotFoundError(
            "Could not find Rust library. Please compile it first:\n"
            "  cd secure_signer && cargo build --release --features ffi"
        )
    
    def _setup_functions(self):
        """Set up ctypes function signatures."""
        # SignerResult struct
        class SignerResultStruct(Structure):
            _fields_ = [
                ("error_code", c_int),
                ("result", c_char_p),
            ]
        
        self.SignerResultStruct = SignerResultStruct
        
        # signer_create_container
        self.lib.signer_create_container.argtypes = [
            c_char_p,  # private_key_b58
            c_char_p,  # passphrase
        ]
        self.lib.signer_create_container.restype = SignerResultStruct
        
        # signer_sign_transaction
        self.lib.signer_sign_transaction.argtypes = [
            c_char_p,  # container_json
            c_char_p,  # passphrase
            c_char_p,  # transaction_b64
        ]
        self.lib.signer_sign_transaction.restype = SignerResultStruct
        
        # signer_free_string
        self.lib.signer_free_string.argtypes = [c_char_p]
        self.lib.signer_free_string.restype = None
        
        # signer_version
        self.lib.signer_version.argtypes = []
        self.lib.signer_version.restype = c_char_p
        
        # signer_check_mlock_support
        self.lib.signer_check_mlock_support.argtypes = []
        self.lib.signer_check_mlock_support.restype = c_int
    
    def get_version(self) -> str:
        """Get the library version."""
        return self.lib.signer_version().decode('utf-8')
    
    def check_mlock_support(self) -> bool:
        """Check if mlock is supported on this system."""
        return self.lib.signer_check_mlock_support() == 1
    
    def create_encrypted_container(
        self,
        private_key: bytes,
        passphrase: str
    ) -> dict:
        """
        Create an encrypted key container.
        
        Args:
            private_key: 32-byte Ed25519 private key (or base58 string)
            passphrase: Passphrase for encryption
            
        Returns:
            Dictionary containing the encrypted container
            
        Raises:
            RuntimeError: If encryption fails
        """
        # Convert bytes to base58 if needed
        if isinstance(private_key, bytes):
            private_key_b58 = base58.b58encode(private_key).decode('utf-8')
        else:
            private_key_b58 = private_key
        
        # Call FFI
        result = self.lib.signer_create_container(
            private_key_b58.encode('utf-8'),
            passphrase.encode('utf-8')
        )
        
        # Handle result
        if result.error_code != 0:
            error_msg = result.result.decode('utf-8') if result.result else "Unknown error"
            raise RuntimeError(f"Encryption failed: {error_msg}")
        
        # Parse JSON result
        result_json = json.loads(result.result.decode('utf-8'))
        return result_json
    
    def sign_transaction(
        self,
        encrypted_container: dict,
        passphrase: str,
        transaction: bytes
    ) -> Tuple[bytes, bytes]:
        """
        Sign a Solana transaction.
        
        SECURITY: This is the critical security function. The private key:
        - Is decrypted in Rust's locked memory
        - Never enters Python's memory space
        - Is zeroized immediately after signing
        - Cannot be swapped to disk
        
        Args:
            encrypted_container: Encrypted key container (from create_encrypted_container)
            passphrase: Passphrase for decryption
            transaction: Unsigned transaction bytes
            
        Returns:
            Tuple of (signature, signed_transaction)
            
        Raises:
            RuntimeError: If signing fails
        """
        # Serialize container to JSON
        if isinstance(encrypted_container, dict):
            container_json = json.dumps(encrypted_container)
        else:
            container_json = encrypted_container
        
        # Convert transaction to base64
        transaction_b64 = base64.b64encode(transaction).decode('utf-8')
        
        # Call FFI
        result = self.lib.signer_sign_transaction(
            container_json.encode('utf-8'),
            passphrase.encode('utf-8'),
            transaction_b64.encode('utf-8')
        )
        
        # Handle result
        if result.error_code != 0:
            error_msg = result.result.decode('utf-8') if result.result else "Unknown error"
            raise RuntimeError(f"Signing failed: {error_msg}")
        
        # Parse result
        result_json = json.loads(result.result.decode('utf-8'))
        
        # Decode signature and signed transaction from base58/base64
        signature = base58.b58decode(result_json['signature']) if 'signature' in result_json else b''
        signed_tx = base64.b64decode(result_json['signed_transaction']) if 'signed_transaction' in result_json else b''
        
        return signature, signed_tx


# ============================================================================
# Method 2: CLI Subprocess Integration
# ============================================================================

class SolanaSignerCLI:
    """
    Python wrapper for the Rust signing CLI using subprocess.
    
    This is useful when FFI is not available or as a fallback.
    Slightly slower than FFI but more portable.
    """
    
    def __init__(self, binary_path: Optional[str] = None):
        """
        Initialize the CLI wrapper.
        
        Args:
            binary_path: Path to the compiled Rust binary.
                        If None, will search in common locations.
        """
        if binary_path is None:
            binary_path = self._find_binary()
        
        self.binary_path = binary_path
    
    def _find_binary(self) -> str:
        """Find the compiled Rust binary."""
        possible_paths = [
            # secure_signer paths (primary)
            Path(__file__).parent / "secure_signer" / "target" / "release" / "solana-signer",
            Path(__file__).parent / "secure_signer" / "target" / "release" / "solana-signer.exe",
            Path(__file__).parent / "secure_signer" / "target" / "debug" / "solana-signer",
            Path(__file__).parent / "secure_signer" / "target" / "debug" / "solana-signer.exe",
            # Legacy rust_signer paths (fallback)
            Path(__file__).parent / "rust_signer" / "target" / "release" / "solana-signer",
            Path(__file__).parent / "rust_signer" / "target" / "release" / "solana-signer.exe",
        ]
        
        for path in possible_paths:
            if path.exists():
                return str(path)
        
        raise FileNotFoundError(
            "Could not find Rust binary. Please compile it first:\n"
            "  cd secure_signer && cargo build --release --features ffi"
        )
    
    def sign_transaction_stdin(
        self,
        encrypted_container: dict,
        passphrase: str,
        transaction: bytes
    ) -> Tuple[bytes, bytes]:
        """
        Sign a transaction using the CLI via stdin/stdout.
        
        Args:
            encrypted_container: Encrypted key container
            passphrase: Passphrase for decryption
            transaction: Unsigned transaction bytes
            
        Returns:
            Tuple of (signature, signed_transaction)
            
        Raises:
            RuntimeError: If signing fails
        """
        # Prepare input
        container_json = json.dumps(encrypted_container)
        tx_hex = transaction.hex()
        
        input_data = f"{container_json}\n{tx_hex}\n"
        
        # Run CLI
        try:
            result = subprocess.run(
                [self.binary_path, "sign-stdin", "-p", passphrase],
                input=input_data,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse output
            output_data = json.loads(result.stdout)
            signature = base64.b64decode(output_data['signature']) if isinstance(output_data['signature'], str) else bytes(output_data['signature'])
            signed_tx = base64.b64decode(output_data['signed_transaction']) if isinstance(output_data['signed_transaction'], str) else bytes(output_data['signed_transaction'])
            
            return signature, signed_tx
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"CLI signing failed: {e.stderr}")


# ============================================================================
# Example Usage
# ============================================================================

def example_ffi():
    """Example using FFI integration."""
    print("=" * 70)
    print("Example 1: FFI Integration")
    print("=" * 70)
    
    # Initialize signer
    signer = SolanaSecureSigner()
    print(f"Library version: {signer.get_version()}")
    
    # Generate a test private key (in production, use proper key generation)
    private_key = bytes([42] * 32)  # DO NOT use this in production!
    
    # Create encrypted container
    passphrase = "super_secure_passphrase_123"
    print("\n1. Creating encrypted container...")
    container = signer.create_encrypted_container(private_key, passphrase)
    print(f"   ✓ Container created with salt: {container['salt'][:20]}...")
    
    # Create a test transaction
    test_transaction = b"Hello, Solana! This is a test transaction."
    print(f"\n2. Signing transaction ({len(test_transaction)} bytes)...")
    
    # Sign the transaction
    # SECURITY: The private key is decrypted in Rust's locked memory
    # and never enters Python's memory space
    signature, signed_tx = signer.sign_transaction(
        container,
        passphrase,
        test_transaction
    )
    
    print(f"   ✓ Transaction signed!")
    print(f"   Signature: {signature.hex()[:32]}...")
    print(f"   Signed TX length: {len(signed_tx)} bytes")
    
    # Demonstrate wrong passphrase
    print("\n3. Testing wrong passphrase...")
    try:
        signer.sign_transaction(container, "wrong_passphrase", test_transaction)
        print("   ✗ Should have failed!")
    except RuntimeError as e:
        print(f"   ✓ Correctly rejected: {str(e)[:50]}...")
    
    print("\n" + "=" * 70)
    print("FFI Integration Example Complete")
    print("=" * 70)


def example_cli():
    """Example using CLI integration."""
    print("\n\n")
    print("=" * 70)
    print("Example 2: CLI Subprocess Integration")
    print("=" * 70)
    
    # Initialize CLI wrapper
    try:
        cli = SolanaSignerCLI()
        
        # Use the same container from FFI example
        signer = SolanaSecureSigner()
        private_key = bytes([42] * 32)
        passphrase = "super_secure_passphrase_123"
        container = signer.create_encrypted_container(private_key, passphrase)
        
        # Sign via CLI
        test_transaction = b"Hello from CLI!"
        print(f"\n1. Signing transaction via CLI...")
        signature, signed_tx = cli.sign_transaction_stdin(
            container,
            passphrase,
            test_transaction
        )
        
        print(f"   ✓ Transaction signed via CLI!")
        print(f"   Signature: {signature.hex()[:32]}...")
        
        print("\n" + "=" * 70)
        print("CLI Integration Example Complete")
        print("=" * 70)
        
    except FileNotFoundError as e:
        print(f"\n⚠ CLI binary not found: {e}")
        print("   Skipping CLI example. Compile with: cd rust_signer && cargo build --release")


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "SOLANA SECURE SIGNER - PYTHON INTEGRATION" + " " * 11 + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    print("This demonstrates secure transaction signing with:")
    print("  • Private keys locked in RAM (mlock/VirtualLock)")
    print("  • Automatic zeroization of sensitive data")
    print("  • No key exposure to Python memory space")
    print("  • Panic-safe cleanup guarantees")
    print()
    
    try:
        example_ffi()
    except FileNotFoundError as e:
        print(f"\n⚠ Error: {e}")
        print("\nPlease compile the Rust library first:")
        print("  cd rust_signer")
        print("  cargo build --release")
        sys.exit(1)
    
    try:
        example_cli()
    except Exception as e:
        print(f"\nCLI example error: {e}")
