"""
Network Operations - RPC communication with Solana blockchain

B - Love U 3000
"""

import asyncio
from typing import Optional, Tuple
import httpx

from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.transaction import VersionedTransaction

from config import SOLANA_RPC_URL, LAMPORTS_PER_SOL
from src.ui import print_success, print_error, print_info, print_warning, create_spinner


class SolanaNetwork:
    def __init__(self, rpc_url: str = None):
        self.rpc_url = rpc_url or SOLANA_RPC_URL
        self.client = httpx.Client(timeout=30.0)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def _make_rpc_request(self, method: str, params: list = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or []
        }
        
        response = self.client.post(
            self.rpc_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()
    
    def get_balance(self, public_key: str) -> Optional[float]:
        try:
            result = self._make_rpc_request("getBalance", [public_key])
            
            if "error" in result:
                print_error(f"RPC Error: {result['error']['message']}")
                return None
            
            lamports = result.get("result", {}).get("value", 0)
            return lamports / LAMPORTS_PER_SOL
        except httpx.HTTPError as e:
            print_error(f"Network error: {e}")
            return None
        except Exception as e:
            print_error(f"Error getting balance: {e}")
            return None
    
    def get_latest_blockhash(self) -> Optional[Tuple[str, int]]:
        try:
            # B - Love U 3000
            result = self._make_rpc_request(
                "getLatestBlockhash",
                [{"commitment": "finalized"}]
            )
            
            if "error" in result:
                print_error(f"RPC Error: {result['error']['message']}")
                return None
            
            value = result.get("result", {}).get("value", {})
            blockhash = value.get("blockhash")
            last_valid_height = value.get("lastValidBlockHeight")
            
            if blockhash:
                return blockhash, last_valid_height
            return None
        except Exception as e:
            print_error(f"Error getting blockhash: {e}")
            return None
    
    def get_minimum_balance_for_rent_exemption(self, data_size: int = 0) -> Optional[int]:
        try:
            result = self._make_rpc_request(
                "getMinimumBalanceForRentExemption",
                [data_size]
            )
            
            if "error" in result:
                return None
            
            return result.get("result")
        except Exception:
            return None
    
    def send_transaction(self, signed_tx_base64: str) -> Optional[str]:
        try:
            # B - Love U 3000
            result = self._make_rpc_request(
                "sendTransaction",
                [
                    signed_tx_base64,
                    {"encoding": "base64", "preflightCommitment": "finalized"}
                ]
            )
            
            if "error" in result:
                error_msg = result['error'].get('message', 'Unknown error')
                print_error(f"Transaction failed: {error_msg}")
                return None
            
            signature = result.get("result")
            if signature:
                print_success(f"Transaction sent successfully!")
                print_info(f"Signature: {signature}")
                return signature
            return None
        except Exception as e:
            print_error(f"Error sending transaction: {e}")
            return None
    
    def confirm_transaction(self, signature: str, max_retries: int = 30) -> bool:
        for i in range(max_retries):
            try:
                result = self._make_rpc_request(
                    "getSignatureStatuses",
                    [[signature]]
                )
                
                if "error" in result:
                    continue
                
                statuses = result.get("result", {}).get("value", [])
                if statuses and statuses[0]:
                    status = statuses[0]
                    if status.get("confirmationStatus") in ["confirmed", "finalized"]:
                        return True
                    if status.get("err"):
                        print_error(f"Transaction error: {status['err']}")
                        return False
                
                import time
                time.sleep(1)
            except Exception:
                import time
                time.sleep(1)
        
        return False
    
    def request_airdrop(self, public_key: str, amount_sol: float = 1.0) -> Optional[str]:
        try:
            lamports = int(amount_sol * LAMPORTS_PER_SOL)
            result = self._make_rpc_request(
                "requestAirdrop",
                [public_key, lamports]
            )
            
            if "error" in result:
                print_error(f"Airdrop failed: {result['error']['message']}")
                return None
            
            signature = result.get("result")
            if signature:
                print_success(f"Airdrop requested: {amount_sol} SOL")
                return signature
            return None
        except Exception as e:
            print_error(f"Airdrop error: {e}")
            return None
    
    def get_account_info(self, public_key: str) -> Optional[dict]:
        try:
            result = self._make_rpc_request(
                "getAccountInfo",
                [public_key, {"encoding": "base64"}]
            )
            
            if "error" in result:
                return None
            
            return result.get("result", {}).get("value")
        except Exception:
            return None
    
    def is_connected(self) -> bool:
        try:
            result = self._make_rpc_request("getHealth")
            return result.get("result") == "ok"
        except Exception:
            return False
    
    def get_network_info(self) -> dict:
        try:
            version = self._make_rpc_request("getVersion")
            slot = self._make_rpc_request("getSlot")
            epoch = self._make_rpc_request("getEpochInfo")
            
            return {
                "version": version.get("result", {}).get("solana-core", "Unknown"),
                "slot": slot.get("result", 0),
                "epoch": epoch.get("result", {}).get("epoch", 0),
                "rpc_url": self.rpc_url
            }
        except Exception:
            return {"error": "Could not fetch network info"}
    
    def get_transaction_history(self, public_key: str, limit: int = 10) -> Optional[list]:
        """Get recent transaction history for an address"""
        try:
            result = self._make_rpc_request(
                "getSignaturesForAddress",
                [public_key, {"limit": limit}]
            )
            
            if "error" in result:
                print_error(f"Failed to get transaction history: {result['error']['message']}")
                return None
            
            signatures = result.get("result", [])
            return signatures
        except Exception as e:
            print_error(f"Error getting transaction history: {e}")
            return None
    
    def get_transaction_details(self, signature: str) -> Optional[dict]:
        """Get detailed information about a specific transaction"""
        try:
            result = self._make_rpc_request(
                "getTransaction",
                [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            )
            
            if "error" in result:
                return None
            
            return result.get("result")
        except Exception:
            return None
    
    def close(self):
        self.client.close()
