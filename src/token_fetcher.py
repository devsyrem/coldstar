"""
Token Balance Fetcher - Get SPL token balances and metadata
"""

import httpx
from typing import Optional, List, Dict
from config import SOLANA_RPC_URL

# Known SPL token mint addresses (Mainnet + Devnet)
KNOWN_TOKENS = {
    # Mainnet USDC
    "USDC": {
        "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "decimals": 6,
        "symbol": "USDC",
        "icon": "🔵"
    },
    # Devnet USDC
    "USDC_DEVNET": {
        "mint": "Gh9ZwEmdLJ8DscKNTkTqPbNwLNNBjuSzaG9Vp2KGtKJr",
        "decimals": 6,
        "symbol": "USDC",
        "icon": "🔵"
    },
    "USDT": {
        "mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        "decimals": 6,
        "symbol": "USDT",
        "icon": "🟢"
    },
    "RAY": {
        "mint": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "decimals": 6,
        "symbol": "RAY",
        "icon": "🟡"
    },
    "BONK": {
        "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "decimals": 5,
        "symbol": "BONK",
        "icon": "🐶"
    },
    "JUP": {
        "mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        "decimals": 6,
        "symbol": "JUP",
        "icon": "🪐"
    }
}

class TokenFetcher:
    """Fetch SPL token balances for a wallet"""

    def __init__(self, rpc_url: str = SOLANA_RPC_URL):
        self.rpc_url = rpc_url
        self.client = httpx.Client(timeout=30.0)

    def get_token_accounts(self, wallet_address: str) -> List[Dict]:
        """Get all SPL token accounts for a wallet"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    wallet_address,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed"}
                ]
            }

            response = self.client.post(self.rpc_url, json=payload)
            data = response.json()

            if "result" in data and "value" in data["result"]:
                return data["result"]["value"]
            return []

        except Exception as e:
            print(f"Error fetching token accounts: {e}")
            return []

    def parse_token_balance(self, token_account: Dict) -> Optional[Dict]:
        """Parse a token account into balance info"""
        try:
            parsed = token_account.get("account", {}).get("data", {}).get("parsed", {})
            info = parsed.get("info", {})

            mint = info.get("mint")
            token_amount = info.get("tokenAmount", {})
            ui_amount = token_amount.get("uiAmount", 0)
            decimals = token_amount.get("decimals", 0)

            # Find token info
            token_info = None
            for symbol, data in KNOWN_TOKENS.items():
                if data["mint"] == mint:
                    token_info = data
                    break

            # Return ALL tokens (including 0 balance) if they have a token account
            return {
                "mint": mint,
                "symbol": token_info["symbol"] if token_info else "Unknown",
                "icon": token_info["icon"] if token_info else "🪙",
                "balance": ui_amount if ui_amount is not None else 0.0,
                "decimals": decimals,
                "is_known": token_info is not None
            }

        except Exception as e:
            print(f"Error parsing token: {e}")

        return None

    def get_all_token_balances(self, wallet_address: str) -> List[Dict]:
        """Get all token balances for a wallet - shows all tokens with accounts (including 0 balance)"""
        accounts = self.get_token_accounts(wallet_address)
        balances = []

        # Parse all token accounts (includes 0 balance tokens)
        for account in accounts:
            parsed = self.parse_token_balance(account)
            if parsed:
                balances.append(parsed)

        # Sort by known tokens first, then by balance
        balances.sort(key=lambda x: (not x["is_known"], -x["balance"]))

        return balances

    def close(self):
        """Close the HTTP client"""
        self.client.close()
