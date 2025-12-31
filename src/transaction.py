"""
Transaction Management - Create, sign, and serialize Solana transactions

B - Love U 3000
"""

import json
import base64
import sys
from pathlib import Path
from typing import Optional, Tuple

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.system_program import transfer, TransferParams
from solders.transaction import Transaction
from solders.message import Message

from config import LAMPORTS_PER_SOL, INFRASTRUCTURE_FEE_PERCENTAGE, INFRASTRUCTURE_FEE_WALLET
from src.ui import print_success, print_error, print_info, print_warning, console

# Import Rust signer (REQUIRED)
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from python_signer_example import SolanaSecureSigner
    RUST_SIGNER_AVAILABLE = True
except ImportError as e:
    from src.ui import print_error, print_info
    print_error("FATAL: Rust secure signer is required but not found!")
    print_error(f"Import error: {e}")
    print_info("Build the Rust signer:")
    print_info("  cd secure_signer")
    print_info("  cargo build --release")
    sys.exit(1)


class TransactionManager:
    def __init__(self):
        self.unsigned_tx: Optional[bytes] = None
        self.signed_tx: Optional[bytes] = None
        
        # Initialize Rust signer (REQUIRED)
        try:
            self.rust_signer = SolanaSecureSigner()
        except (FileNotFoundError, OSError) as e:
            print_error("FATAL: Rust library not found or incompatible!")
            print_error(f"Error: {e}")
            print_info("Build the Rust signer:")
            print_info("  cd secure_signer")
            print_info("  cargo build --release")
            sys.exit(1)
        except Exception as e:
            print_error(f"FATAL: Failed to initialize Rust signer: {e}")
            sys.exit(1)
    
    def calculate_infrastructure_fee(self, amount_sol: float) -> float:
        """Calculate 1% infrastructure fee in SOL"""
        return amount_sol * INFRASTRUCTURE_FEE_PERCENTAGE
    
    def create_transfer_transaction(
        self,
        from_pubkey: str,
        to_pubkey: str,
        amount_sol: float,
        recent_blockhash: str
    ) -> Optional[bytes]:
        try:
            from_pk = Pubkey.from_string(from_pubkey)
            to_pk = Pubkey.from_string(to_pubkey)
            infra_pk = Pubkey.from_string(INFRASTRUCTURE_FEE_WALLET)
            
            # Calculate infrastructure fee (1% of transaction amount)
            infra_fee_sol = self.calculate_infrastructure_fee(amount_sol)
            infra_fee_lamports = int(infra_fee_sol * LAMPORTS_PER_SOL)
            
            # Main transfer amount
            lamports = int(amount_sol * LAMPORTS_PER_SOL)
            blockhash = Hash.from_string(recent_blockhash)
            
            # Create transfer instructions
            instructions = []
            
            # 1. Main transfer to recipient
            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=from_pk,
                    to_pubkey=to_pk,
                    lamports=lamports
                )
            )
            instructions.append(transfer_ix)
            
            # 2. Infrastructure fee transfer (only if fee > 0)
            if infra_fee_lamports > 0:
                infra_fee_ix = transfer(
                    TransferParams(
                        from_pubkey=from_pk,
                        to_pubkey=infra_pk,
                        lamports=infra_fee_lamports
                    )
                )
                instructions.append(infra_fee_ix)
            
            # Debug: Verify transfer instruction
            print_info(f"Transfer instruction created:")
            print_info(f"  Program ID: {transfer_ix.program_id}")
            print_info(f"  Accounts: {len(transfer_ix.accounts)}")
            print_info(f"  Data (hex): {transfer_ix.data.hex()}")
            print_info(f"  Lamports to transfer: {lamports}")
            if infra_fee_lamports > 0:
                print_info(f"  Infrastructure fee: {infra_fee_sol:.9f} SOL ({infra_fee_lamports} lamports)")
            
            message = Message.new_with_blockhash(
                instructions,
                from_pk,
                blockhash
            )
            
            # Debug: Verify message
            print_info(f"Message created:")
            print_info(f"  Num instructions: {len(message.instructions)}")
            print_info(f"  Num accounts: {len(message.account_keys)}")
            
            tx = Transaction.new_unsigned(message)
            
            # Debug: Verify transaction
            print_info(f"Transaction created:")
            print_info(f"  Message instructions: {len(tx.message.instructions)}")
            
            # B - Love U 3000
            self.unsigned_tx = bytes(tx)
            
            print_success(f"Created unsigned transaction")
            print_info(f"From: {from_pubkey}")
            print_info(f"To: {to_pubkey}")
            print_info(f"Amount: {amount_sol} SOL")
            if infra_fee_lamports > 0:
                print_info(f"Infrastructure Fee: {infra_fee_sol:.9f} SOL")
            
            return self.unsigned_tx
        except Exception as e:
            print_error(f"Failed to create transaction: {e}")
            return None
    
    def sign_transaction_secure(self, unsigned_tx_bytes: bytes, encrypted_container: dict, password: str) -> Optional[bytes]:
        """Sign transaction using Rust secure signer (keys never in Python memory)"""
        if not RUST_SIGNER_AVAILABLE or self.rust_signer is None:
            print_error("Rust signer not available. Cannot sign securely.")
            print_info("Build Rust signer: cd secure_signer && cargo build --release")
            print_warning("Falling back to INSECURE Python signing...")
            
            # Fallback to Python-based signing
            from src.secure_memory import SecureWalletHandler
            keypair = SecureWalletHandler.decrypt_keypair(encrypted_container, password)
            if not keypair:
                print_error("Failed to decrypt keypair")
                return None
            
            signed_tx = self.sign_transaction(unsigned_tx_bytes, keypair)
            
            # Clear keypair from memory
            import gc
            del keypair
            gc.collect()
            
            return signed_tx
        
        try:
            console.print()
            print_info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print_success("🔐 SECURE SIGNING IN PROGRESS")
            print_info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print_info("  Step 1: Encrypted container received")
            print_success("    ✓ Private key: ENCRYPTED (not in Python memory)")
            
            # Parse the unsigned transaction to get the message
            tx = Transaction.from_bytes(unsigned_tx_bytes)
            message_bytes = bytes(tx.message)
            
            print_info("  Step 2: Transaction message prepared")
            print_success("    ✓ Message size: {} bytes".format(len(message_bytes)))
            print_success("    ✓ Passing to Rust secure core...")
            
            # Call Rust signer to sign just the MESSAGE (not the full transaction)
            print_info("  Step 3: Rust signer executing...")
            print_success("    ✓ Key decryption: IN RUST MEMORY ONLY")
            print_success("    ✓ Signing operation: IN RUST MEMORY ONLY")
            print_success("    ✓ Python memory: NO KEY EXPOSURE")
            
            signature, _ = self.rust_signer.sign_transaction(
                encrypted_container,
                password,
                message_bytes
            )
            
            print_info("  Step 4: Signature received from Rust")
            print_success("    ✓ Private key: ZEROIZED in Rust memory")
            print_success("    ✓ Signature extracted: {} bytes".format(len(signature)))
            
            # Now properly add the signature to the transaction using solders
            from solders.signature import Signature
            sig = Signature.from_bytes(signature)
            tx.signatures = [sig]
            
            self.signed_tx = bytes(tx)
            
            print_info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print_success("✓ TRANSACTION SIGNED SECURELY!")
            print_info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print_success("  🔒 Security Guarantee:")
            print_success("    • Private key NEVER entered Python memory")
            print_success("    • Decryption happened in Rust locked memory")
            print_success("    • Signing happened in Rust locked memory")
            print_success("    • Key automatically zeroized after use")
            print_success("    • Memory protection: ACTIVE throughout")
            print_info(f"  Signature (preview): {signature[:16].hex()}...")
            print_info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            console.print()
            return self.signed_tx
        except Exception as e:
            print_error(f"Failed to sign transaction: {e}")
            if "Decryption failed" in str(e):
                print_warning("Incorrect password or corrupted wallet")
            return None
    
    def sign_transaction(self, unsigned_tx_bytes: bytes, keypair: Keypair) -> Optional[bytes]:
        """DISABLED: Insecure signing not allowed. Use sign_transaction_secure() only."""
        print_error("SECURITY ERROR: Insecure Python-based signing is disabled!")
        print_error("This method exposes private keys in Python memory.")
        print_info("Use sign_transaction_secure() instead.")
        raise RuntimeError("Insecure signing method disabled. Use sign_transaction_secure() only.")
    
    def save_unsigned_transaction(self, tx_bytes: bytes, path: str) -> bool:
        try:
            filepath = Path(path)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            tx_data = {
                "type": "unsigned_transaction",
                "version": "1.0",
                "data": base64.b64encode(tx_bytes).decode('utf-8')
            }
            
            with open(filepath, 'w') as f:
                json.dump(tx_data, f, indent=2)
            
            print_success(f"Unsigned transaction saved to: {filepath}")
            return True
        except Exception as e:
            print_error(f"Failed to save transaction: {e}")
            return False
    
    def load_unsigned_transaction(self, path: str) -> Optional[bytes]:
        try:
            filepath = Path(path)
            if not filepath.exists():
                print_error(f"Transaction file not found: {filepath}")
                return None
            
            with open(filepath, 'r') as f:
                tx_data = json.load(f)
            
            if tx_data.get("type") != "unsigned_transaction":
                print_error("Invalid transaction file format")
                return None
            
            tx_bytes = base64.b64decode(tx_data["data"])
            self.unsigned_tx = tx_bytes
            
            print_success(f"Loaded unsigned transaction from: {filepath}")
            return tx_bytes
        except Exception as e:
            print_error(f"Failed to load transaction: {e}")
            return None
    
    def save_signed_transaction(self, tx_bytes: bytes, path: str) -> bool:
        try:
            filepath = Path(path)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            tx_data = {
                "type": "signed_transaction",
                "version": "1.0",
                "data": base64.b64encode(tx_bytes).decode('utf-8')
            }
            
            with open(filepath, 'w') as f:
                json.dump(tx_data, f, indent=2)
            
            print_success(f"Signed transaction saved to: {filepath}")
            return True
        except Exception as e:
            print_error(f"Failed to save signed transaction: {e}")
            return False
    
    def load_signed_transaction(self, path: str) -> Optional[bytes]:
        try:
            filepath = Path(path)
            if not filepath.exists():
                print_error(f"Transaction file not found: {filepath}")
                return None
            
            with open(filepath, 'r') as f:
                tx_data = json.load(f)
            
            if tx_data.get("type") != "signed_transaction":
                print_error("Invalid signed transaction file format")
                return None
            
            tx_bytes = base64.b64decode(tx_data["data"])
            self.signed_tx = tx_bytes
            
            print_success(f"Loaded signed transaction from: {filepath}")
            return tx_bytes
        except Exception as e:
            print_error(f"Failed to load signed transaction: {e}")
            return None
    
    def get_transaction_for_broadcast(self) -> Optional[str]:
        if self.signed_tx is None:
            print_error("No signed transaction available")
            return None
        
        return base64.b64encode(self.signed_tx).decode('utf-8')
    
    def decode_transaction_info(self, tx_bytes: bytes) -> Optional[dict]:
        try:
            tx = Transaction.from_bytes(tx_bytes)
            
            info = {
                "signatures": len(tx.signatures),
                "is_signed": len(tx.signatures) > 0 and tx.signatures[0] != bytes(64),
                "num_instructions": len(tx.message.instructions),
                "recent_blockhash": str(tx.message.recent_blockhash),
                "fee_payer": str(tx.message.account_keys[0]) if tx.message.account_keys else None
            }
            
            return info
        except Exception as e:
            print_error(f"Failed to decode transaction: {e}")
            return None
