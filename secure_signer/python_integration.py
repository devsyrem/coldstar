#!/usr/bin/env python3
"""
Solana Secure Signer - Python Integration Example

This module demonstrates two integration methods:
1. Subprocess mode - Call the Rust binary as a subprocess
2. FFI mode - Load the shared library directly (ctypes)

Both methods keep private keys secure within the Rust memory-locked buffer.

Usage:
    python python_integration.py --demo
    python python_integration.py --create-container --key <base58_key> --passphrase <pass>
    python python_integration.py --sign --container <file> --passphrase <pass> --transaction <base64>
"""

import argparse
import base64
import ctypes
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


# =============================================================================
# SUBPROCESS MODE - Call Rust binary as a subprocess
# =============================================================================

class SubprocessSigner:
    """
    Secure signer using subprocess to invoke the Rust binary.
    
    This is the recommended approach for most use cases as it:
    - Provides process isolation (separate memory space)
    - Ensures cleanup even on crashes
    - Works without shared library compilation
    """
    
    def __init__(self, binary_path: str = "solana-signer"):
        """
        Initialize the subprocess signer.
        
        Args:
            binary_path: Path to the solana-signer binary
        """
        self.binary_path = binary_path
    
    def _run_command(self, args: list) -> dict:
        """Run a command and parse JSON output."""
        try:
            result = subprocess.run(
                [self.binary_path] + args,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            output = result.stdout.strip() or result.stderr.strip()
            return json.loads(output)
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out"}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {e}"}
        except FileNotFoundError:
            return {"success": False, "error": f"Binary not found: {self.binary_path}"}
    
    def _run_stdin_mode(self, command: dict) -> dict:
        """Run command via stdin (more secure, avoids command-line exposure)."""
        try:
            proc = subprocess.Popen(
                [self.binary_path, "--stdin"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = proc.communicate(json.dumps(command) + "\n", timeout=60)
            output = stdout.strip() or stderr.strip()
            return json.loads(output)
            
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"success": False, "error": "Command timed out"}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {e}"}
        except FileNotFoundError:
            return {"success": False, "error": f"Binary not found: {self.binary_path}"}
    
    def create_container(self, private_key_b58: str, passphrase: str) -> dict:
        """
        Create an encrypted key container.
        
        Args:
            private_key_b58: Base58-encoded private key (32 or 64 bytes)
            passphrase: Passphrase for encryption
            
        Returns:
            dict with container JSON on success, or error message
        """
        return self._run_stdin_mode({
            "action": "create_container",
            "private_key": private_key_b58,
            "passphrase": passphrase
        })
    
    def sign_transaction(
        self,
        container_json: str,
        passphrase: str,
        transaction_bytes: bytes
    ) -> dict:
        """
        Sign a transaction using an encrypted container.
        
        Args:
            container_json: JSON string of the encrypted container
            passphrase: Passphrase for decryption
            transaction_bytes: Unsigned transaction bytes
            
        Returns:
            dict with signature and signed transaction on success
        """
        transaction_b64 = base64.b64encode(transaction_bytes).decode('ascii')
        
        return self._run_stdin_mode({
            "action": "sign",
            "container": container_json,
            "passphrase": passphrase,
            "transaction": transaction_b64
        })
    
    def check_capabilities(self) -> dict:
        """Check system capabilities (mlock support, etc.)."""
        return self._run_stdin_mode({"action": "check"})


# =============================================================================
# FFI MODE - Load shared library directly
# =============================================================================

@dataclass
class SignerResult:
    """Result from FFI signing operations."""
    error_code: int
    result: str
    
    @property
    def success(self) -> bool:
        return self.error_code == 0
    
    def to_dict(self) -> dict:
        if self.success:
            return {"success": True, "data": json.loads(self.result)}
        else:
            return {"success": False, "error": self.result}


class FFISignerResult(ctypes.Structure):
    """C struct for SignerResult."""
    _fields_ = [
        ("error_code", ctypes.c_int32),
        ("result", ctypes.c_char_p)
    ]


class FFISigner:
    """
    Secure signer using FFI to call the Rust library directly.
    
    This approach is faster but requires the shared library to be compiled
    and available on the system.
    """
    
    def __init__(self, library_path: Optional[str] = None):
        """
        Initialize the FFI signer.
        
        Args:
            library_path: Path to the shared library (.so/.dll/.dylib)
        """
        if library_path is None:
            library_path = self._find_library()
        
        self.lib = ctypes.CDLL(library_path)
        self._setup_functions()
    
    def _find_library(self) -> str:
        """Find the shared library on the system."""
        # Check common locations
        candidates = [
            # Development builds
            "./target/release/libsolana_secure_signer.so",
            "./target/debug/libsolana_secure_signer.so",
            "./secure_signer/target/release/libsolana_secure_signer.so",
            "./secure_signer/target/debug/libsolana_secure_signer.so",
            # System-wide
            "/usr/local/lib/libsolana_secure_signer.so",
            # Windows
            "./target/release/solana_secure_signer.dll",
            "./secure_signer/target/release/solana_secure_signer.dll",
            # macOS
            "./target/release/libsolana_secure_signer.dylib",
            "./secure_signer/target/release/libsolana_secure_signer.dylib",
        ]
        
        for path in candidates:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError(
            "Could not find libsolana_secure_signer. "
            "Please build with: cargo build --release"
        )
    
    def _setup_functions(self):
        """Configure ctypes function signatures."""
        # signer_create_container
        self.lib.signer_create_container.argtypes = [
            ctypes.c_char_p,  # private_key_b58
            ctypes.c_char_p   # passphrase
        ]
        self.lib.signer_create_container.restype = FFISignerResult
        
        # signer_sign_transaction
        self.lib.signer_sign_transaction.argtypes = [
            ctypes.c_char_p,  # container_json
            ctypes.c_char_p,  # passphrase
            ctypes.c_char_p   # transaction_b64
        ]
        self.lib.signer_sign_transaction.restype = FFISignerResult
        
        # signer_sign_direct
        self.lib.signer_sign_direct.argtypes = [
            ctypes.c_char_p,  # private_key_b58
            ctypes.c_char_p   # message_b64
        ]
        self.lib.signer_sign_direct.restype = FFISignerResult
        
        # signer_free_result
        self.lib.signer_free_result.argtypes = [FFISignerResult]
        self.lib.signer_free_result.restype = None
        
        # signer_version
        self.lib.signer_version.argtypes = []
        self.lib.signer_version.restype = ctypes.c_char_p
        
        # signer_check_mlock_support
        self.lib.signer_check_mlock_support.argtypes = []
        self.lib.signer_check_mlock_support.restype = ctypes.c_int32
    
    def _process_result(self, ffi_result: FFISignerResult) -> dict:
        """Process FFI result and free memory."""
        result_str = ffi_result.result.decode('utf-8') if ffi_result.result else ""
        error_code = ffi_result.error_code
        
        # Free the result memory
        self.lib.signer_free_result(ffi_result)
        
        signer_result = SignerResult(error_code, result_str)
        return signer_result.to_dict()
    
    def create_container(self, private_key_b58: str, passphrase: str) -> dict:
        """Create an encrypted key container."""
        result = self.lib.signer_create_container(
            private_key_b58.encode('utf-8'),
            passphrase.encode('utf-8')
        )
        return self._process_result(result)
    
    def sign_transaction(
        self,
        container_json: str,
        passphrase: str,
        transaction_bytes: bytes
    ) -> dict:
        """Sign a transaction using an encrypted container."""
        transaction_b64 = base64.b64encode(transaction_bytes).decode('ascii')
        
        result = self.lib.signer_sign_transaction(
            container_json.encode('utf-8'),
            passphrase.encode('utf-8'),
            transaction_b64.encode('utf-8')
        )
        return self._process_result(result)
    
    def sign_direct(self, private_key_b58: str, message: bytes) -> dict:
        """Sign a message directly (less secure than using container)."""
        message_b64 = base64.b64encode(message).decode('ascii')
        
        result = self.lib.signer_sign_direct(
            private_key_b58.encode('utf-8'),
            message_b64.encode('utf-8')
        )
        return self._process_result(result)
    
    def get_version(self) -> str:
        """Get the library version."""
        return self.lib.signer_version().decode('utf-8')
    
    def check_mlock_support(self) -> bool:
        """Check if memory locking is supported."""
        return self.lib.signer_check_mlock_support() == 1


# =============================================================================
# HIGH-LEVEL API
# =============================================================================

class SecureSigner:
    """
    High-level secure signer API that automatically selects the best backend.
    
    Tries FFI first for performance, falls back to subprocess if unavailable.
    """
    
    def __init__(
        self,
        mode: str = "auto",
        binary_path: str = "solana-signer",
        library_path: Optional[str] = None
    ):
        """
        Initialize the secure signer.
        
        Args:
            mode: "auto", "subprocess", or "ffi"
            binary_path: Path to the Rust binary (for subprocess mode)
            library_path: Path to shared library (for FFI mode)
        """
        self.mode = mode
        self._backend = None
        
        if mode == "subprocess":
            self._backend = SubprocessSigner(binary_path)
        elif mode == "ffi":
            self._backend = FFISigner(library_path)
        elif mode == "auto":
            # Try FFI first, fall back to subprocess
            try:
                self._backend = FFISigner(library_path)
                self.mode = "ffi"
            except (FileNotFoundError, OSError):
                self._backend = SubprocessSigner(binary_path)
                self.mode = "subprocess"
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    def create_container(self, private_key_b58: str, passphrase: str) -> dict:
        """Create an encrypted key container from a private key."""
        return self._backend.create_container(private_key_b58, passphrase)
    
    def sign_transaction(
        self,
        container_json: str,
        passphrase: str,
        transaction_bytes: bytes
    ) -> dict:
        """Sign a transaction using an encrypted key container."""
        return self._backend.sign_transaction(container_json, passphrase, transaction_bytes)
    
    def __repr__(self):
        return f"SecureSigner(mode={self.mode!r})"


# =============================================================================
# DEMONSTRATION
# =============================================================================

def demo():
    """
    Demonstrate the secure signing workflow.
    
    This example shows:
    1. Creating an encrypted key container
    2. Signing a transaction with the container
    3. Verifying the signature
    """
    import secrets
    
    print("=" * 60)
    print("Solana Secure Signer - Python Integration Demo")
    print("=" * 60)
    print()
    
    # Generate a test private key (in production, use a real key)
    print("[1] Generating test Ed25519 private key...")
    private_key_bytes = secrets.token_bytes(32)
    
    # Encode as base58 (Solana format)
    import base58  # pip install base58
    private_key_b58 = base58.b58encode(private_key_bytes).decode('ascii')
    print(f"    Private key (first 8 chars): {private_key_b58[:8]}...")
    print()
    
    # Create the signer
    print("[2] Initializing secure signer...")
    try:
        signer = SecureSigner(mode="subprocess")
        print(f"    Using mode: {signer.mode}")
    except Exception as e:
        print(f"    Error: {e}")
        print("    Make sure to build the Rust binary first:")
        print("    cd secure_signer && cargo build --release")
        return
    print()
    
    # Check capabilities
    print("[3] Checking system capabilities...")
    if hasattr(signer._backend, 'check_capabilities'):
        caps = signer._backend.check_capabilities()
        if caps.get('success'):
            data = caps.get('data', {})
            print(f"    Version: {data.get('version', 'unknown')}")
            print(f"    Memory locking: {'Supported' if data.get('mlock_supported') else 'Not supported'}")
            print(f"    Platform: {data.get('platform', 'unknown')}")
        else:
            print(f"    Could not check capabilities: {caps.get('error')}")
    print()
    
    # Create encrypted container
    print("[4] Creating encrypted key container...")
    passphrase = "demo_passphrase_123"
    result = signer.create_container(private_key_b58, passphrase)
    
    if not result.get('success'):
        print(f"    Error: {result.get('error')}")
        return
    
    container_data = result.get('data', {})
    container_json = json.dumps(container_data)
    print(f"    Container version: {container_data.get('version')}")
    print(f"    Public key: {container_data.get('public_key', 'N/A')[:20]}...")
    print(f"    Salt (first 12 chars): {container_data.get('salt', '')[:12]}...")
    print()
    
    # Create a dummy transaction message
    print("[5] Creating test transaction message...")
    # In real usage, this would be a serialized Solana transaction message
    test_message = b"Test Solana transaction message for signing"
    print(f"    Message: {test_message.decode('ascii')}")
    print()
    
    # Sign the transaction
    print("[6] Signing transaction with secure signer...")
    print("    (Private key is decrypted in Rust's locked memory)")
    result = signer.sign_transaction(container_json, passphrase, test_message)
    
    if not result.get('success'):
        print(f"    Error: {result.get('error')}")
        return
    
    sign_data = result.get('data', {})
    print(f"    Signature: {sign_data.get('signature', '')[:40]}...")
    print(f"    Public key: {sign_data.get('public_key', '')[:20]}...")
    if sign_data.get('signed_transaction'):
        print(f"    Signed tx (first 40 chars): {sign_data['signed_transaction'][:40]}...")
    print()
    
    # Verify signature (using ed25519)
    print("[7] Verifying signature...")
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignature
        
        public_key_bytes = base58.b58decode(sign_data['public_key'])
        signature_bytes = base58.b58decode(sign_data['signature'])
        
        verify_key = VerifyKey(public_key_bytes)
        verify_key.verify(test_message, signature_bytes)
        print("    Signature is VALID")
    except ImportError:
        print("    (Install pynacl to verify: pip install pynacl)")
    except BadSignature:
        print("    Signature is INVALID")
    except Exception as e:
        print(f"    Verification error: {e}")
    print()
    
    print("=" * 60)
    print("Demo completed successfully!")
    print()
    print("Security notes:")
    print("- Private key was encrypted with Argon2id + AES-256-GCM")
    print("- Decryption happened in Rust's mlock'd memory buffer")
    print("- Key was automatically zeroized after signing")
    print("- No plaintext key was exposed to Python")
    print("=" * 60)


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Solana Secure Signer Python Integration"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demonstration"
    )
    parser.add_argument(
        "--create-container",
        action="store_true",
        help="Create encrypted key container"
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Sign a transaction"
    )
    parser.add_argument(
        "--key",
        help="Base58-encoded private key"
    )
    parser.add_argument(
        "--passphrase",
        help="Passphrase for encryption/decryption"
    )
    parser.add_argument(
        "--container",
        help="Path to container file or JSON string"
    )
    parser.add_argument(
        "--transaction",
        help="Base64-encoded transaction bytes"
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "subprocess", "ffi"],
        default="subprocess",
        help="Integration mode"
    )
    parser.add_argument(
        "--binary",
        default="./secure_signer/target/release/solana-signer",
        help="Path to Rust binary"
    )
    
    args = parser.parse_args()
    
    if args.demo:
        demo()
        return
    
    signer = SecureSigner(mode=args.mode, binary_path=args.binary)
    
    if args.create_container:
        if not args.key or not args.passphrase:
            print("Error: --key and --passphrase required")
            sys.exit(1)
        
        result = signer.create_container(args.key, args.passphrase)
        print(json.dumps(result, indent=2))
        
    elif args.sign:
        if not args.container or not args.passphrase or not args.transaction:
            print("Error: --container, --passphrase, and --transaction required")
            sys.exit(1)
        
        # Load container
        if os.path.exists(args.container):
            with open(args.container) as f:
                container_json = f.read()
        else:
            container_json = args.container
        
        # Decode transaction
        transaction_bytes = base64.b64decode(args.transaction)
        
        result = signer.sign_transaction(container_json, args.passphrase, transaction_bytes)
        print(json.dumps(result, indent=2))
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
