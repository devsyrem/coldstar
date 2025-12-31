#!/usr/bin/env python3
"""
Utility script to upgrade unencrypted wallet to encrypted format
"""

import json
import sys
from pathlib import Path

from src.wallet import WalletManager
from src.ui import print_success, print_error, print_info, print_warning

def upgrade_wallet(wallet_path: str):
    """Upgrade an unencrypted wallet to encrypted format"""
    wallet_path = Path(wallet_path)
    
    if not wallet_path.exists():
        print_error(f"Wallet file not found: {wallet_path}")
        return False
    
    # Check if already encrypted
    with open(wallet_path, 'r') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        print_info("Wallet is already encrypted!")
        return True
    
    print_warning("⚠️  This wallet is in UNENCRYPTED format (insecure)")
    print_info("Upgrading to encrypted format...")
    print_info("")
    
    # Create wallet manager
    wallet_manager = WalletManager()
    wallet_manager.set_wallet_directory(str(wallet_path.parent))
    
    # Load the keypair from unencrypted format
    from solders.keypair import Keypair
    secret_bytes = bytes(data)
    keypair = Keypair.from_bytes(secret_bytes)
    wallet_manager.keypair = keypair
    
    print_success(f"✓ Loaded keypair: {keypair.pubkey()}")
    
    # Create backup
    backup_path = wallet_path.with_suffix('.unencrypted.backup')
    wallet_path.rename(backup_path)
    print_info(f"✓ Original wallet backed up to: {backup_path}")
    
    # Save with encryption (will prompt for password)
    if wallet_manager.save_keypair(str(wallet_path)):
        print_success("✓ Wallet successfully upgraded to encrypted format!")
        print_warning("")
        print_warning("IMPORTANT: Remember your password!")
        print_warning("Without it, you cannot access your funds.")
        return True
    else:
        # Restore backup if save failed
        backup_path.rename(wallet_path)
        print_error("Failed to upgrade wallet. Original restored.")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        wallet_path = sys.argv[1]
    else:
        wallet_path = "local_wallet/keypair.json"
    
    print_info(f"Upgrading wallet: {wallet_path}")
    upgrade_wallet(wallet_path)
