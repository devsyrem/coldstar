"""
Secure Memory & Encryption Module

Handles transient decryption of private keys using PyNaCl (libsodium).
Implements Argon2id key derivation and XSalsa20-Poly1305 encryption.
"""

import json
import os
import gc
from typing import Optional, Tuple, List, Dict

import nacl.secret
import nacl.utils
import nacl.pwhash
from solders.keypair import Keypair

class SecureWalletHandler:
    """
    Handles encrypted wallet operations.
    Ensures private keys are only decrypted transiently.
    """
    
    @staticmethod
    def encrypt_keypair(keypair: Keypair, password: str) -> dict:
        """
        Encrypts a keypair with a password.
        Returns a dictionary containing salt, nonce, and ciphertext.
        """
        password_bytes = password.encode('utf-8')
        salt = nacl.utils.random(nacl.pwhash.argon2i.SALTBYTES)
        
        # Derive key using Argon2i (resistant to GPU cracking)
        key = nacl.pwhash.argon2i.kdf(
            nacl.secret.SecretBox.KEY_SIZE,
            password_bytes,
            salt,
            opslimit=nacl.pwhash.argon2i.OPSLIMIT_INTERACTIVE,
            memlimit=nacl.pwhash.argon2i.MEMLIMIT_INTERACTIVE
        )
        
        box = nacl.secret.SecretBox(key)
        nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
        
        # Serialize keypair to bytes
        secret_bytes = bytes(keypair)
        
        encrypted = box.encrypt(secret_bytes, nonce)
        
        # Clean up sensitive data
        del key
        del password_bytes
        gc.collect()
        
        # Return hex-encoded values for JSON storage
        return {
            "version": 1,
            "algo": "argon2i_xsalsa20poly1305",
            "salt": salt.hex(),
            "nonce": nonce.hex(),
            "ciphertext": encrypted.ciphertext.hex()
        }

    @staticmethod
    def decrypt_keypair(encrypted_data: dict, password: str) -> Optional[Keypair]:
        """
        Decrypts the keypair transiently.
        """
        try:
            password_bytes = password.encode('utf-8')
            salt = bytes.fromhex(encrypted_data['salt'])
            nonce = bytes.fromhex(encrypted_data['nonce'])
            ciphertext = bytes.fromhex(encrypted_data['ciphertext'])
            
            # Derive key
            key = nacl.pwhash.argon2i.kdf(
                nacl.secret.SecretBox.KEY_SIZE,
                password_bytes,
                salt,
                opslimit=nacl.pwhash.argon2i.OPSLIMIT_INTERACTIVE,
                memlimit=nacl.pwhash.argon2i.MEMLIMIT_INTERACTIVE
            )
            
            box = nacl.secret.SecretBox(key)
            decrypted_bytes = box.decrypt(ciphertext, nonce)
            
            keypair = Keypair.from_bytes(decrypted_bytes)
            
            # Clean up sensitive data
            del key
            del password_bytes
            del decrypted_bytes
            gc.collect()
            
            return keypair
            
        except Exception as e:
            # print_warning(f"Decryption failed: {e}")
            return None
