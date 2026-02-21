#!/usr/bin/env python3
"""
Solana Cold Wallet USB Tool
Main CLI Entry Point

A terminal-based tool for creating and managing Solana cold wallets on USB drives.

B - Love U 3000
"""

import sys
import os
import tempfile
import subprocess
from pathlib import Path

from rich.console import Console

from config import APP_NAME, APP_VERSION, SOLANA_RPC_URL
from src.ui import (
    print_banner, print_success, print_error, print_info, print_warning,
    print_section_header, print_wallet_info, print_transaction_summary,
    print_device_list, select_menu_option, get_text_input, get_float_input,
    confirm_dangerous_action, print_explorer_link, clear_screen, console,
    print_step
)
from src.wallet import WalletManager, create_wallet_structure
from src.usb import USBManager
from src.network import SolanaNetwork
from src.transaction import TransactionManager
from src.iso_builder import ISOBuilder


class SolanaColdWalletCLI:
    def __init__(self):
        self.wallet_manager = WalletManager()
        self.usb_manager = USBManager()
        self.network = SolanaNetwork()
        self.transaction_manager = TransactionManager()
        self.iso_builder = ISOBuilder()
        
        self.current_usb_device = None
        self.current_public_key = None
        self.usb_is_cold_wallet = False
    
    def _check_usb_for_wallet(self, mount_point: str) -> tuple:
        """Check if mounted USB has a cold wallet with pubkey.txt"""
        pubkey_path = Path(mount_point) / "wallet" / "pubkey.txt"
        if pubkey_path.exists():
            with open(pubkey_path, 'r') as f:
                return True, f.read().strip()
        return False, None
    
    def _display_wallet_balance(self):
        if not self.current_public_key:
            return
        
        print_section_header("WALLET STATUS")
        balance = self.network.get_balance(self.current_public_key)
        print_wallet_info(self.current_public_key, balance)
        console.print()
    
    def run(self):
        # B - Love U 3000
        while True:
            try:
                self.main_menu()
            except KeyboardInterrupt:
                console.print("\n")
                print_info("Exiting...")
                self.cleanup()
                sys.exit(0)
            except Exception as e:
                print_error(f"Error: {e}")
                continue
    
    def _draw_header(self):
        clear_screen()
        print_banner()
        print_info(f"Network: {SOLANA_RPC_URL}")
        if self.network.is_connected():
            print_success("Status: Connected")
        else:
            print_warning("Status: Offline")
        console.print()
    
    def main_menu(self):
        self._draw_header()
        devices = self.usb_manager.detect_usb_devices()
        
        if not devices:
            self._no_usb_menu()
        elif self.usb_is_cold_wallet and self.current_public_key:
            self._wallet_menu()
        else:
            self._usb_detected_menu(devices)
    
    def _no_usb_menu(self):
        print_section_header("NO USB DEVICE DETECTED")
        print_warning("Please connect a USB drive to continue.")
        console.print()
        
        options = [
            "1. Refresh (Check for USB)",
            "2. Network Status",
            "0. Exit"
        ]
        
        choice = select_menu_option(options, "Select an option:")
        
        if choice is None:
            return
        
        choice_num = choice.split(".")[0].strip()
        
        if choice_num == "2":
            self._draw_header()
            self.show_network_status()
            self._wait_for_key()
        elif choice_num == "0":
            self.exit_app()
    
    def _wait_for_key(self):
        console.print()
        console.input("[dim]Press Enter to continue...[/dim]")
    
    def _usb_detected_menu(self, devices):
        print_section_header("USB DEVICE DETECTED")
        print_device_list(devices)
        console.print()
        
        options = [
            "1. Flash Cold Wallet OS to USB",
            "2. Mount USB (Check for existing wallet)",
            "3. Network Status",
            "0. Exit"
        ]
        
        choice = select_menu_option(options, "Select an option:")
        
        if choice is None:
            return
        
        choice_num = choice.split(".")[0].strip()
        
        if choice_num == "1":
            self._draw_header()
            self.flash_cold_wallet()
            self._wait_for_key()
        elif choice_num == "2":
            self._mount_and_check_wallet(devices)
        elif choice_num == "3":
            self._draw_header()
            self.show_network_status()
            self._wait_for_key()
        elif choice_num == "0":
            self.exit_app()
    
    def _wallet_menu(self):
        """Launch the modern TUI interface when wallet is mounted"""
        # Launch the new TUI interface
        from tui_wallet import ColdstarLiveWallet

        app = ColdstarLiveWallet()
        app.run()

        # If TUI unmounted the wallet, clear local state
        if getattr(app, "did_unmount", False):
            self.usb_is_cold_wallet = False
            self.current_public_key = None
            self.current_usb_device = None
            self.usb_manager.mount_point = None

        # When TUI exits, return to main loop
        return
    
    def flash_cold_wallet(self):
        """Build and flash cold wallet OS to USB"""
        print_section_header("FLASH COLD WALLET OS")
        
        print_info("This process will:")
        print_info("  1. Download Alpine Linux minimal root filesystem (~50MB)")
        print_info("  2. Customize it with Solana signing tools")
        print_info("  3. Create bootable cold wallet structure")
        print_info("  4. Flash to USB (erases all existing data)")
        print_info("  5. Generate keypair and wallet on the USB")
        console.print()
        
        print_info("Detected USB devices:")
        devices = self.usb_manager.detect_usb_devices()
        if not devices:
            print_error("No USB devices found. Please insert a USB drive.")
            return
        
        print_device_list(devices)
        console.print()
        
        # Select device to flash
        if len(devices) == 1:
            device = devices[0]
            print_info(f"Auto-selected: {device['device']}")
        else:
            device_options = [f"{i+1}. {d['device']} ({d['size']})" for i, d in enumerate(devices)]
            device_options.append("Cancel")
            
            selection = select_menu_option(device_options, "Select USB device to flash:")
            
            if not selection or "Cancel" in selection:
                print_info("Flash operation cancelled")
                return
            
            idx = int(selection.split(".")[0]) - 1
            device = devices[idx]
        
        console.print()
        print_warning(f"⚠️  ALL DATA ON {device['device']} WILL BE ERASED! ⚠️")
        console.print()
        
        # Simple yes/no confirmation is sufficient
        from src.ui import select_menu_option
        confirm_choice = select_menu_option(
            ["Yes, erase and flash", "Cancel"],
            f"Erase and flash {device['device']}?"
        )
        
        if not confirm_choice or "Cancel" in confirm_choice:
            print_info("Flash operation cancelled")
            return
        
        console.print()
        print_info("Starting cold wallet creation...")
        print_info("This may take several minutes...")
        console.print()
        
        # Build and flash the cold wallet
        try:
            import time
            
            # Show progress through the build process
            print_step(1, 7, "Initializing ISO builder...")
            time.sleep(0.5)
            
            # The ISOBuilder will handle the actual animated steps
            result_path = self.iso_builder.build_complete_iso("./output")
            
            if not result_path or not result_path.exists():
                print_error("Failed to build cold wallet image")
                return
            
            console.print()
            print_success(f"Cold wallet image built: {result_path.name}")
            console.print()
            
            # Flash to USB
            print_info(f"Flashing to {device['device']}...")
            console.print()
            
            if self.iso_builder.flash_to_usb(device['device'], str(result_path)):
                console.print()
                print_success("✓ Cold wallet USB created successfully!")
                
                # Display the generated public key if available
                if self.iso_builder.generated_pubkey:
                    console.print()
                    from rich.panel import Panel
                    wallet_info = f"""[bold green]Wallet Generated Successfully![/bold green]

[yellow]Public Key (Wallet Address):[/yellow]
[bold white]{self.iso_builder.generated_pubkey}[/bold white]

[bold cyan]This wallet is now ready to receive and send SOL![/bold cyan]

Write down or photograph this address to receive payments."""
                    console.print(Panel(wallet_info, title="✓ Wallet Ready", border_style="green"))
                
                console.print()
                print_info("Next steps:")
                print_info("  1. Safely remove the USB drive")
                print_info("  2. The wallet is ready - you can send SOL to the address above")
                print_info("  3. For air-gapped signing, boot from this USB on an offline computer")
                print_info("  4. Keep the USB offline and secure when not in use")
                console.print()
                
                from rich.panel import Panel
                security_msg = """[bold yellow]SECURITY REMINDERS:[/bold yellow]

• This USB should ONLY be used on air-gapped computers
• Never connect to internet-connected machines for signing
• Store in a secure location when not in use
• Consider creating multiple backup copies
• Test the USB boot process before relying on it"""
                
                console.print(Panel(security_msg, title="⚠️  Security", border_style="yellow"))
            else:
                print_error("Failed to flash USB drive")
                print_info("You can try flashing manually using the image in ./output/")
        
        except Exception as e:
            print_error(f"Flash operation failed: {e}")
            import traceback
            if "--debug" in sys.argv:
                traceback.print_exc()
    
    def _mount_and_check_wallet(self, devices):
        if len(devices) == 1:
            idx = 0
            device = devices[0]
            print_info(f"Auto-selected: {device['device']} ({device['size']})")
        else:
            device_options = [f"{i+1}. {d['device']} ({d['size']})" for i, d in enumerate(devices)]
            device_options.append("Cancel")
            
            selection = select_menu_option(device_options, "Select device to mount:")
            
            if not selection or "Cancel" in selection:
                return
            
            idx = int(selection.split(".")[0]) - 1
            device = devices[idx]
        
        # Select the device first so USB manager has the context
        self.usb_manager.select_device(idx)
        
        mount_point = self.usb_manager.mount_device(device['device'])
        if mount_point:
            is_wallet, pubkey = self._check_usb_for_wallet(mount_point)
            if is_wallet:
                self.usb_is_cold_wallet = True
                self.current_public_key = pubkey
                self.current_usb_device = device
                print_success("Cold wallet found on USB!")
                print_info(f"Public Key: {pubkey}")
                
                # Load the wallet (will prompt for password if encrypted)
                wallet_dir = Path(mount_point) / "wallet"
                self.wallet_manager.set_wallet_directory(str(wallet_dir))
                
                # We don't necessarily need to load the PRIVATE key just to check balance.
                # But if we do, we should clear it immediately.
                # However, the original code called _display_wallet_balance() which uses public key.
                # So we are fine not loading the private key here yet.
                self._display_wallet_balance()
            else:
                print_info("No wallet found on this USB.")
                # Offer to create a wallet
                create_choice = select_menu_option(
                    ["Yes, create a new wallet", "No, go back"],
                    "Would you like to create a new wallet on this USB?"
                )
                if create_choice and "Yes" in create_choice:
                    self._create_wallet_on_usb(mount_point, device)
    
    def _create_wallet_on_usb(self, mount_point: str, device: dict):
        """Generate and save a new wallet on the USB drive"""
        print_section_header("CREATING NEW WALLET")
        
        wallet_dir = Path(mount_point) / "wallet"
        wallet_dir.mkdir(parents=True, exist_ok=True)
        
        self.wallet_manager.set_wallet_directory(str(wallet_dir))
        
        print_info("Generating new Solana keypair...")
        keypair, public_key = self.wallet_manager.generate_keypair()
        
        console.print()
        
        # save_keypair will prompt for password which serves as confirmation
        if self.wallet_manager.save_keypair():
            self.usb_is_cold_wallet = True
            self.current_public_key = public_key
            self.current_usb_device = device
            
            print_success("✓ Wallet created successfully!")
            console.print()
            print_info(f"Public Key: {public_key}")
            print_info(f"Wallet saved to: {wallet_dir}")
            console.print()
            print_warning("IMPORTANT: Keep this USB drive secure and offline!")
            print_warning("Anyone with the password can control your funds.")
            console.print()
            self._display_wallet_balance()
        else:
            print_error("Failed to create wallet")
    
    def quick_send_transaction(self):
        """Create, sign, and broadcast a transaction in one step"""
        print_section_header("QUICK SEND")
        
        if not self.current_public_key:
            print_error("No wallet connected. Mount a USB with a cold wallet first.")
            return
        
        # Load keypair
        wallet_dir = Path(self.usb_manager.mount_point) / "wallet"
        keypair_path = wallet_dir / "keypair.json"
        
        if not keypair_path.exists():
            print_error("Keypair not found on USB")
            return
        
        # Load wallet (without password prompt)
        self.wallet_manager.load_keypair(str(keypair_path))
        # Note: load_keypair now returns None for encrypted wallets, which is fine
        # We'll get the password later after SEND confirmation
            
        try:
            from_address = self.current_public_key
            print_info(f"From: {from_address}")
            
            balance = self.network.get_balance(from_address)
            if balance is not None:
                print_info(f"Current balance: {balance:.9f} SOL")
            
            console.print()
            
            to_address = get_text_input("Enter recipient's public key: ")
            if not self.wallet_manager.validate_address(to_address):
                print_error("Invalid recipient address")
                return
            
            amount = get_float_input("Enter amount to send (SOL): ")
            if amount <= 0:
                print_error("Amount must be greater than 0")
                return
            
            if balance is not None and amount >= balance:
                print_warning(f"Amount ({amount} SOL) exceeds available balance ({balance} SOL)")
                if not confirm_dangerous_action("Proceed anyway?", "YES"):
                    return
            
            console.print()
            print_transaction_summary(from_address, to_address, amount)
            console.print()
            
            # Password IS the confirmation
            from src.ui import get_password_input
            password = get_password_input("Type your password to confirm transaction:")
            
            if not password:
                print_info("Transaction cancelled")
                return
            
            # Get fresh blockhash
            blockhash_result = self.network.get_latest_blockhash()
            if not blockhash_result:
                print_error("Failed to get blockhash from network")
                return
            
            blockhash, _ = blockhash_result
            
            # Create transaction
            tx_bytes = self.transaction_manager.create_transfer_transaction(
                from_address, to_address, amount, blockhash
            )
            
            if not tx_bytes:
                return
            
            # Sign transaction securely with Rust signer
            print_info("Signing transaction securely...")
            
            # Load encrypted container from wallet
            encrypted_container = self.wallet_manager.load_encrypted_container(str(keypair_path), password)
            if not encrypted_container:
                print_error("Failed to load encrypted wallet container")
                return
            
            signed_tx = self.transaction_manager.sign_transaction_secure(tx_bytes, encrypted_container, password)
            
            if not signed_tx:
                return
            
            # Broadcast transaction
            print_info("Broadcasting transaction...")
            
            import base64
            tx_base64 = base64.b64encode(signed_tx).decode('utf-8')
            
            signature = self.network.send_transaction(tx_base64)
            
            if signature:
                print_success("Transaction sent!")
                print_info(f"Signature: {signature}")
                print_info("Waiting for confirmation...")
                
                if self.network.confirm_transaction(signature):
                    print_success("✓ Transaction confirmed!")
                    console.print()
                    
                    # Refresh balance after successful transaction
                    import time
                    time.sleep(2)  # Wait a bit for balance to update on chain
                    new_balance = self.network.get_balance(from_address)
                    if new_balance is not None:
                        print_success(f"Updated balance: {new_balance:.9f} SOL")
                    
                    print_explorer_link(signature)
                else:
                    print_warning("Transaction sent but confirmation timed out")
                    print_info("Check the explorer for final status")
                    console.print()
                    print_explorer_link(signature)
        
        finally:
            # CRITICAL: Clear key from memory
            self.wallet_manager.clear_memory()
    
    def sign_transaction(self):
        """Sign a transaction using the local wallet"""
        print_section_header("SIGN TRANSACTION (LOCAL)")
        
        if not self.current_public_key:
            print_error("No wallet connected. Mount a USB with a cold wallet first.")
            return
            
        wallet_dir = Path(self.usb_manager.mount_point) / "wallet"
        keypair_path = wallet_dir / "keypair.json"
        
        if not keypair_path.exists():
            print_error("Keypair not found on USB")
            return
        
        # Load encrypted container for secure signing
        encrypted_container = self.wallet_manager.load_encrypted_container(str(keypair_path))
        if not encrypted_container:
            print_error("Failed to load encrypted wallet container")
            return
            
        # Select transaction file
        if not self.usb_manager.mount_point:
             print_error("No USB mounted.")
             return

        inbox_dir = Path(self.usb_manager.mount_point) / "inbox"
        outbox_dir = Path(self.usb_manager.mount_point) / "outbox"
        outbox_dir.mkdir(exist_ok=True)
        
        unsigned_files = list(inbox_dir.glob("unsigned_*.json")) if inbox_dir.exists() else []
        
        if not unsigned_files:
            print_warning("No unsigned transactions found in USB inbox.")
            print_info("Create a transaction first using 'Send SOL' option.")
            return
            
        file_options = [f.name for f in unsigned_files]
        file_options.append("Cancel")
        
        selection = select_menu_option(file_options, "Select transaction to sign:")
        
        if not selection or "Cancel" in selection:
            return
            
        tx_path = inbox_dir / selection
        
        # Get password for secure signing - use cached password if available
        password = self.wallet_manager.get_cached_password()
        if password is None:
            from src.ui import get_password_input
            password = get_password_input("Enter wallet password for secure signing:")
            
        try:
            # Load and sign the transaction
            unsigned_tx = self.transaction_manager.load_unsigned_transaction(str(tx_path))
            if not unsigned_tx:
                return
            
            print_info("Signing transaction securely with Rust signer...")
            signed_tx = self.transaction_manager.sign_transaction_secure(unsigned_tx, encrypted_container, password)
            
            if signed_tx:
                # Save to outbox with signed_ prefix
                output_name = selection.replace("unsigned_", "signed_")
                output_path = outbox_dir / output_name
                
                if self.transaction_manager.save_signed_transaction(signed_tx, str(output_path)):
                    print_success("Transaction signed and saved to outbox!")
                    print_info(f"Signed file: {output_name}")
                    print_info("You can now broadcast this transaction.")
                    
                    # Auto-delete the unsigned transaction to keep inbox clean
                    tx_path.unlink()
                    print_success("Unsigned transaction removed from inbox.")
        finally:
            self.wallet_manager.clear_memory()

    
    def create_unsigned_transaction(self):
        print_section_header("CREATE UNSIGNED TRANSACTION")
        
        if not self.current_public_key:
            print_error("No wallet connected. Mount a USB with a cold wallet first.")
            return
        
        from_address = self.current_public_key
        print_info(f"From: {from_address}")
        
        balance = self.network.get_balance(from_address)
        if balance is not None:
            print_info(f"Current balance: {balance:.9f} SOL")
        
        console.print()
        
        to_address = get_text_input("Enter recipient's public key: ")
        if not self.wallet_manager.validate_address(to_address):
            print_error("Invalid recipient address")
            return
        
        amount = get_float_input("Enter amount to send (SOL): ")
        if amount <= 0:
            print_error("Amount must be greater than 0")
            return
        
        if balance is not None and amount >= balance:
            print_warning(f"Amount ({amount} SOL) exceeds available balance ({balance} SOL)")
            if not confirm_dangerous_action("Proceed anyway?", "YES"):
                return
        
        console.print()
        print_transaction_summary(from_address, to_address, amount)
        console.print()
        
        blockhash_result = self.network.get_latest_blockhash()
        if not blockhash_result:
            print_error("Failed to get blockhash from network")
            return
        
        blockhash, _ = blockhash_result
        
        tx_bytes = self.transaction_manager.create_transfer_transaction(
            from_address, to_address, amount, blockhash
        )
        
        if tx_bytes:
            if self.usb_manager.mount_point:
                inbox_dir = Path(self.usb_manager.mount_point) / "inbox"
                inbox_dir.mkdir(exist_ok=True)
                output_dir = inbox_dir
            else:
                output_dir = Path("./transactions")
                output_dir.mkdir(exist_ok=True)
            
            import time
            filename = f"unsigned_tx_{int(time.time())}.json"
            output_path = output_dir / filename
            
            if self.transaction_manager.save_unsigned_transaction(tx_bytes, str(output_path)):
                console.print()
                print_success("Unsigned transaction created!")
                print_info(f"File: {output_path}")
                if self.usb_manager.mount_point:
                    print_info("Transaction saved to USB inbox.")
                    print_info("Boot the USB on an air-gapped computer to sign.")
                else:
                    print_info("Copy this file to your cold wallet's /inbox directory for signing")
    
    def sign_transaction(self):
        print_section_header("SIGN TRANSACTION")
        
        if not self.usb_manager.mount_point:
            print_error("No USB mounted. Mount your cold wallet USB first.")
            return
        
        inbox_dir = Path(self.usb_manager.mount_point) / "inbox"
        outbox_dir = Path(self.usb_manager.mount_point) / "outbox"
        outbox_dir.mkdir(exist_ok=True)
        
        # Look for unsigned transactions in inbox
        unsigned_files = list(inbox_dir.glob("unsigned_*.json")) if inbox_dir.exists() else []
        
        if not unsigned_files:
            print_warning("No unsigned transactions found in USB inbox.")
            print_info("Create a transaction first using 'Send SOL' option.")
            return
        
        print_success(f"Found {len(unsigned_files)} unsigned transaction(s)")
        console.print()
        
        # Offer signing options
        sign_choice = select_menu_option(
            ["Sign now", "Sign offline later"],
            "How would you like to proceed?"
        )
        
        if not sign_choice or "offline" in sign_choice:
            print_info("Copy unsigned transactions to an air-gapped device for secure signing.")
            return
        
        # Load the wallet for secure signing
        wallet_dir = Path(self.usb_manager.mount_point) / "wallet"
        keypair_path = wallet_dir / "keypair.json"
        
        if not keypair_path.exists():
            print_error("Keypair not found on USB")
            return
        
        # Load encrypted container for secure signing
        encrypted_container = self.wallet_manager.load_encrypted_container(str(keypair_path))
        if not encrypted_container:
            print_error("Failed to load encrypted wallet container")
            return
        
        # Get password - use cached password if available
        password = self.wallet_manager.get_cached_password()
        if password is None:
            from src.ui import get_password_input
            password = get_password_input("Enter wallet password for secure signing:")
        
        # Let user select which transaction to sign
        file_options = [f.name for f in unsigned_files]
        file_options.append("Cancel")
        
        selection = select_menu_option(file_options, "Select transaction to sign:")
        
        if not selection or "Cancel" in selection:
            return
        
        tx_path = inbox_dir / selection
        
        # Load and sign the transaction
        unsigned_tx = self.transaction_manager.load_unsigned_transaction(str(tx_path))
        if not unsigned_tx:
            return
        
        print_info("Signing transaction securely with Rust signer...")
        signed_tx = self.transaction_manager.sign_transaction_secure(unsigned_tx, encrypted_container, password)
        
        if signed_tx:
            # Save to outbox with signed_ prefix
            output_name = selection.replace("unsigned_", "signed_")
            output_path = outbox_dir / output_name
            
            if self.transaction_manager.save_signed_transaction(signed_tx, str(output_path)):
                print_success("Transaction signed and saved to outbox!")
                print_info(f"Signed file: {output_name}")
                print_info("You can now broadcast this transaction.")
                
                # Optionally delete the unsigned transaction
                delete_choice = select_menu_option(
                    ["Yes", "No"],
                    "Delete the unsigned transaction from inbox?"
                )
                
                if delete_choice and "Yes" in delete_choice:
                    tx_path.unlink()
                    print_success("Unsigned transaction removed from inbox.")
    
    def broadcast_transaction(self):
        print_section_header("BROADCAST SIGNED TRANSACTION")
        
        if not self.usb_manager.mount_point:
            print_error("No USB mounted. Mount your cold wallet USB first.")
            return
        
        outbox_dir = Path(self.usb_manager.mount_point) / "outbox"
        
        signed_files = list(outbox_dir.glob("signed_*.json")) if outbox_dir.exists() else []
        
        if not signed_files:
            print_warning("No signed transactions found in USB outbox")
            print_info("Sign transactions on the air-gapped device first.")
            return
        
        file_options = [f.name for f in signed_files]
        file_options.append("Cancel")
        
        selection = select_menu_option(file_options, "Select transaction to broadcast:")
        
        if not selection or "Cancel" in selection:
            return
        
        tx_path = outbox_dir / selection
        
        tx_bytes = self.transaction_manager.load_signed_transaction(str(tx_path))
        if not tx_bytes:
            return
        
        tx_info = self.transaction_manager.decode_transaction_info(tx_bytes)
        if tx_info:
            print_info(f"Transaction has {tx_info['num_instructions']} instruction(s)")
            print_info(f"Signed: {'Yes' if tx_info['is_signed'] else 'No'}")
        
        console.print()
        print_warning("This will broadcast the transaction to the Solana network")
        if not confirm_dangerous_action("Broadcast this transaction?", "BROADCAST"):
            return
        
        tx_base64 = self.transaction_manager.get_transaction_for_broadcast()
        if not tx_base64:
            return
        
        signature = self.network.send_transaction(tx_base64)
        
        if signature:
            print_info("Waiting for confirmation...")
            
            if self.network.confirm_transaction(signature):
                print_success("Transaction confirmed!")
                console.print()
                
                # Refresh balance after successful transaction
                import time
                time.sleep(2)  # Wait for balance to update on chain
                if self.current_public_key:
                    new_balance = self.network.get_balance(self.current_public_key)
                    if new_balance is not None:
                        print_success(f"Updated balance: {new_balance:.9f} SOL")
            else:
                print_warning("Transaction sent but confirmation timed out")
                print_info("Check the explorer for final status")
            
            print_explorer_link(signature)
    
    def view_transaction_history(self):
        """View recent transaction history for the wallet"""
        print_section_header("TRANSACTION HISTORY")
        
        if not self.current_public_key:
            print_error("No wallet connected. Mount a USB with a cold wallet first.")
            return
        
        public_key = self.current_public_key
        print_info(f"Wallet: {public_key}")
        console.print()
        
        limit = get_float_input("Number of transactions to show (1-50): ", 10)
        limit = int(min(max(limit, 1), 50))  # Clamp between 1 and 50
        
        print_info(f"Fetching last {limit} transactions...")
        console.print()
        
        transactions = self.network.get_transaction_history(public_key, limit)
        
        if not transactions:
            print_warning("No transaction history found")
            return
        
        print_success(f"Found {len(transactions)} transaction(s)")
        console.print()
        
        from rich.table import Table
        
        table = Table(title="Recent Transactions", show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Signature", style="cyan", width=50)
        table.add_column("Status", width=12)
        table.add_column("Slot", justify="right", width=10)
        table.add_column("Time", width=20)
        
        for idx, tx in enumerate(transactions, 1):
            signature = tx.get("signature", "Unknown")
            slot = str(tx.get("slot", "N/A"))
            
            # Determine status
            err = tx.get("err")
            if err is None:
                status = "[green]✓ Success[/green]"
            else:
                status = "[red]✗ Failed[/red]"
            
            # Format timestamp
            block_time = tx.get("blockTime")
            if block_time:
                import datetime
                dt = datetime.datetime.fromtimestamp(block_time)
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = "Pending"
            
            # Truncate signature for display
            sig_display = signature[:20] + "..." + signature[-20:] if len(signature) > 44 else signature
            
            table.add_row(
                str(idx),
                sig_display,
                status,
                slot,
                time_str
            )
        
        console.print(table)
        console.print()
        
        # Offer to view details of a specific transaction
        view_details = select_menu_option(
            ["Yes", "No"],
            "View details of a specific transaction?"
        )
        
        if view_details and "Yes" in view_details:
            tx_num = get_float_input(f"Enter transaction number (1-{len(transactions)}): ", 1)
            tx_idx = int(tx_num) - 1
            
            if 0 <= tx_idx < len(transactions):
                signature = transactions[tx_idx]["signature"]
                self._show_transaction_details(signature)
            else:
                print_error("Invalid transaction number")
    
    def _show_transaction_details(self, signature: str):
        """Show detailed information about a specific transaction"""
        console.print()
        print_info(f"Fetching details for transaction: {signature[:20]}...")
        
        details = self.network.get_transaction_details(signature)
        
        if not details:
            print_error("Could not fetch transaction details")
            return
        
        console.print()
        print_success("Transaction Details:")
        console.print()
        
        from rich.panel import Panel
        from rich.json import JSON
        
        # Extract key information
        meta = details.get("meta", {})
        transaction = details.get("transaction", {})
        
        info_text = f"""[bold]Signature:[/bold] {signature}
[bold]Slot:[/bold] {details.get('slot', 'N/A')}
[bold]Block Time:[/bold] {details.get('blockTime', 'N/A')}
[bold]Fee:[/bold] {meta.get('fee', 0) / 1000000000} SOL

[bold]Status:[/bold] {'✓ Success' if meta.get('err') is None else '✗ Failed'}
[bold]Pre Balance:[/bold] {meta.get('preBalances', [0])[0] / 1000000000} SOL
[bold]Post Balance:[/bold] {meta.get('postBalances', [0])[0] / 1000000000} SOL
"""
        
        console.print(Panel(info_text, title="Transaction Info", border_style="cyan"))
        console.print()
        
        # Show explorer link
        print_explorer_link(signature)
    
    def request_airdrop(self):
        print_section_header("REQUEST DEVNET AIRDROP")
        
        if "devnet" not in SOLANA_RPC_URL:
            print_error("Airdrops are only available on Devnet")
            return
        
        if not self.current_public_key:
            print_error("No wallet connected. Mount a USB with a cold wallet first.")
            return
        
        public_key = self.current_public_key
        print_info(f"Wallet: {public_key}")
        
        amount = get_float_input("Enter amount (max 2 SOL): ", 1.0)
        if amount > 2:
            print_warning("Devnet airdrops are limited to 2 SOL")
            amount = 2.0
        
        print_info(f"Requesting {amount} SOL airdrop...")
        
        signature = self.network.request_airdrop(public_key, amount)
        
        if signature:
            print_info("Waiting for confirmation...")
            
            if self.network.confirm_transaction(signature):
                print_success("Airdrop confirmed!")
                console.print()
                
                # Refresh balance after successful airdrop
                import time
                time.sleep(2)  # Wait for balance to update on chain
                balance = self.network.get_balance(public_key)
                if balance is not None:
                    print_success(f"Updated balance: {balance:.9f} SOL")
            else:
                print_warning("Airdrop may still be processing")
            
            print_explorer_link(signature)
    
    def show_network_status(self):
        print_section_header("NETWORK STATUS")
        
        print_info(f"RPC URL: {SOLANA_RPC_URL}")
        
        if self.network.is_connected():
            print_success("Connection: OK")
            
            info = self.network.get_network_info()
            if "error" not in info:
                print_info(f"Solana Version: {info.get('version', 'Unknown')}")
                print_info(f"Current Slot: {info.get('slot', 'Unknown')}")
                print_info(f"Current Epoch: {info.get('epoch', 'Unknown')}")
        else:
            print_error("Connection: FAILED")
            print_info("Check your internet connection or RPC URL")
    
    def exit_app(self):
        print_info("Cleaning up...")
        self.cleanup()
        print_success("Goodbye!")
        sys.exit(0)
    
    def cleanup(self):
        try:
            self.network.close()
            if self.usb_manager.mount_point:
                self.usb_manager.unmount_device()
        except Exception:
            pass


def build_rust_signer():
    """Build the Rust secure signer before running the application."""
    console = Console()
    console.print("🔨 Building Rust Secure Signer...", style="cyan")
    
    # Check if cargo is available
    try:
        result = subprocess.run(
            ["cargo", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        console.print(f"✓ {result.stdout.strip()}", style="green")
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("❌ Rust/Cargo is not installed!", style="red")
        console.print("Install Rust from: https://rustup.rs/", style="yellow")
        console.print("After installation, restart your terminal and run this script again.", style="yellow")
        sys.exit(1)
    
    # Navigate to secure_signer directory
    secure_signer_dir = Path(__file__).parent / "secure_signer"
    if not secure_signer_dir.exists():
        console.print(f"❌ secure_signer directory not found at {secure_signer_dir}!", style="red")
        sys.exit(1)
    
    # Build release version
    console.print("🔧 Compiling release build (this may take a few minutes)...", style="cyan")
    try:
        result = subprocess.run(
            ["cargo", "build", "--release"],
            cwd=secure_signer_dir,
            capture_output=True,
            text=True,
            check=True
        )
        console.print("✅ BUILD SUCCESSFUL!", style="green bold")
        console.print()
    except subprocess.CalledProcessError as e:
        console.print("❌ BUILD FAILED!", style="red bold")
        console.print(e.stderr, style="red")
        sys.exit(1)


def main():
    # Build Rust signer first
    build_rust_signer()
    
    cli = SolanaColdWalletCLI()
    cli.run()


if __name__ == "__main__":
    main()
