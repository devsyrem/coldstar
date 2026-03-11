"""
ZK Proof Engine - Python FFI wrapper for Rust ZK proof operations.

Provides confidential transfer proof generation, verification,
and ElGamal encryption through the secure_signer Rust library.

B - Love U 3000
"""

import json
import base64
import os
from ctypes import CDLL, Structure, c_int, c_char_p, c_uint64
from pathlib import Path
from typing import Optional, Dict, Any


class ZKErrorCode:
    """Error codes from Rust ZK FFI."""
    SUCCESS = 0
    NULL_INPUT = 1
    UTF8_ERROR = 2
    DECODE_ERROR = 3
    PROOF_ERROR = 4
    SERIALIZATION_ERROR = 5


class SignerResultStruct(Structure):
    """Must match Rust SignerResult layout: error_code + result string."""
    _fields_ = [
        ("error_code", c_int),
        ("result", c_char_p),
    ]


class ZKProofEngine:
    """
    Python wrapper for the Rust ZK proof engine (FFI).
    
    Generates and verifies ElGamal-based confidential transfer proofs
    using Ristretto255 curve operations in the secure_signer Rust crate.
    """
    
    def __init__(self, lib_path: Optional[str] = None):
        """
        Load the Rust secure_signer library.
        
        Args:
            lib_path: Explicit path to libsolana_secure_signer.dylib/.so/.dll.
                      If None, searches standard build locations.
        """
        if lib_path is None:
            lib_path = self._find_library()
        
        self.lib = CDLL(str(lib_path))
        self._setup_functions()
    
    def _find_library(self) -> str:
        """Locate the compiled Rust library."""
        base = Path(__file__).parent.parent / "secure_signer" / "target" / "release"
        candidates = [
            base / "libsolana_secure_signer.dylib",
            base / "libsolana_secure_signer.so",
            base / "solana_secure_signer.dll",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        raise FileNotFoundError(
            "ZK library not found. Build with:\n"
            "  cd secure_signer && cargo build --release --features ffi"
        )
    
    def _setup_functions(self):
        """Configure ctypes function signatures for ZK FFI exports."""
        # zk_version()
        self.lib.zk_version.argtypes = []
        self.lib.zk_version.restype = SignerResultStruct
        
        # zk_generate_elgamal_keypair(seed_b58)
        self.lib.zk_generate_elgamal_keypair.argtypes = [c_char_p]
        self.lib.zk_generate_elgamal_keypair.restype = SignerResultStruct
        
        # zk_encrypt_amount(amount, pubkey_b64)
        self.lib.zk_encrypt_amount.argtypes = [c_uint64, c_char_p]
        self.lib.zk_encrypt_amount.restype = SignerResultStruct
        
        # zk_generate_transfer_proof(amount, sender_seed_b58, recipient_b64, auditor_b64)
        self.lib.zk_generate_transfer_proof.argtypes = [
            c_uint64, c_char_p, c_char_p, c_char_p
        ]
        self.lib.zk_generate_transfer_proof.restype = SignerResultStruct
        
        # zk_verify_transfer_proof(proof_json, sender_pubkey_b64)
        self.lib.zk_verify_transfer_proof.argtypes = [c_char_p, c_char_p]
        self.lib.zk_verify_transfer_proof.restype = SignerResultStruct
        
        # zk_prove_ownership(seed_b58)
        self.lib.zk_prove_ownership.argtypes = [c_char_p]
        self.lib.zk_prove_ownership.restype = SignerResultStruct
    
    def _call(self, result: SignerResultStruct) -> Dict[str, Any]:
        """Parse a SignerResult into a Python dict. Raise on error."""
        if result.error_code != ZKErrorCode.SUCCESS:
            msg = result.result.decode("utf-8") if result.result else "Unknown error"
            raise RuntimeError(f"ZK engine error ({result.error_code}): {msg}")
        return json.loads(result.result.decode("utf-8"))
    
    # ── Public API ──────────────────────────────────────────────────────

    def version(self) -> Dict[str, Any]:
        """Return ZK module version and feature list."""
        return self._call(self.lib.zk_version())
    
    def generate_elgamal_keypair(self, ed25519_seed: Optional[bytes] = None) -> Dict[str, str]:
        """
        Generate an ElGamal keypair for confidential transfers.
        
        Args:
            ed25519_seed: Optional 32-byte seed (derives deterministic key).
                          If None, generates a random keypair.
        
        Returns:
            {"public_key": "<base64>", "public_key_hex": "<hex>"}
        """
        if ed25519_seed is not None:
            import base58 as b58
            seed_b58 = b58.b58encode(ed25519_seed).decode("utf-8")
            return self._call(
                self.lib.zk_generate_elgamal_keypair(seed_b58.encode("utf-8"))
            )
        return self._call(self.lib.zk_generate_elgamal_keypair(None))
    
    def encrypt_amount(self, amount: int, public_key_b64: str) -> Dict[str, str]:
        """
        Encrypt an amount under an ElGamal public key.
        
        Args:
            amount: Value to encrypt (lamports).
            public_key_b64: Base64-encoded 32-byte ElGamal public key.
        
        Returns:
            {"ciphertext_b64": "...", "commitment_b64": "...", "handle_b64": "..."}
        """
        return self._call(
            self.lib.zk_encrypt_amount(
                c_uint64(amount),
                public_key_b64.encode("utf-8"),
            )
        )
    
    def generate_transfer_proof(
        self,
        amount: int,
        sender_seed: bytes,
        recipient_pubkey_b64: str,
        auditor_pubkey_b64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a complete confidential transfer proof bundle.
        
        Args:
            amount: Lamports to transfer.
            sender_seed: 32-byte Ed25519 seed for the sender.
            recipient_pubkey_b64: Recipient ElGamal public key (base64).
            auditor_pubkey_b64: Optional auditor ElGamal public key (base64).
        
        Returns:
            Full proof bundle dict with ciphertexts, proofs, and metadata.
        """
        import base58 as b58
        seed_b58 = b58.b58encode(sender_seed).decode("utf-8")
        
        auditor_arg = auditor_pubkey_b64.encode("utf-8") if auditor_pubkey_b64 else None
        
        return self._call(
            self.lib.zk_generate_transfer_proof(
                c_uint64(amount),
                seed_b58.encode("utf-8"),
                recipient_pubkey_b64.encode("utf-8"),
                auditor_arg,
            )
        )
    
    def verify_transfer_proof(
        self,
        proof_bundle_json: str,
        sender_pubkey_b64: str,
    ) -> Dict[str, Any]:
        """
        Verify a confidential transfer proof bundle.
        
        Args:
            proof_bundle_json: JSON-encoded proof bundle.
            sender_pubkey_b64: Sender ElGamal public key (base64).
        
        Returns:
            {"valid": bool, "checks": {"ownership_proof": bool, ...}}
        """
        return self._call(
            self.lib.zk_verify_transfer_proof(
                proof_bundle_json.encode("utf-8"),
                sender_pubkey_b64.encode("utf-8"),
            )
        )
    
    def prove_ownership(self, ed25519_seed: bytes) -> Dict[str, Any]:
        """
        Prove ownership of an ElGamal keypair (Schnorr NIZK).
        
        Args:
            ed25519_seed: 32-byte Ed25519 seed.
        
        Returns:
            {"public_key": "<b64>", "proof": "<b64>", "valid": bool}
        """
        import base58 as b58
        seed_b58 = b58.b58encode(ed25519_seed).decode("utf-8")
        return self._call(
            self.lib.zk_prove_ownership(seed_b58.encode("utf-8"))
        )
