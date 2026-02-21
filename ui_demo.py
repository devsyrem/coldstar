#!/usr/bin/env python3
"""
UI Demo - Shows the current Coldstar UI without needing USB or Rust components
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ui import (
    print_banner, print_success, print_error, print_info, print_warning,
    print_section_header, print_wallet_info, print_transaction_summary,
    print_device_list, select_menu_option, console, print_step
)
from rich.panel import Panel
from rich.table import Table
import time

def demo_ui():
    """Demonstrate the current UI components"""

    # 1. Banner
    console.clear()
    print_banner()
    print_info("Network: https://api.devnet.solana.com")
    print_success("Status: Connected")
    console.print()

    time.sleep(1.5)

    # 2. USB Device Detection
    print_section_header("USB DEVICE DETECTED")

    demo_devices = [
        {
            'device': '/dev/disk2',
            'size': '16GB',
            'model': 'SanDisk Ultra',
            'mountpoint': '/Volumes/COLDSTAR'
        },
        {
            'device': '/dev/disk3',
            'size': '32GB',
            'model': 'Kingston DataTraveler',
            'mountpoint': 'Not mounted'
        }
    ]

    print_device_list(demo_devices)
    console.print()

    time.sleep(1.5)

    # 3. Wallet Info Display
    print_section_header("WALLET STATUS")
    demo_pubkey = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    demo_balance = 12.458392761

    print_wallet_info(demo_pubkey, demo_balance)
    console.print()

    time.sleep(1.5)

    # 4. Transaction Summary
    print_section_header("TRANSACTION PREVIEW")

    from_addr = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    to_addr = "4ZqK8gJZxvqVqTvPFvKxZqJqK7p3qHxPz4sWqB4oGxsj"
    amount = 2.5

    print_transaction_summary(from_addr, to_addr, amount)
    console.print()

    time.sleep(1.5)

    # 5. Status Messages
    print_section_header("STATUS INDICATORS")

    print_success("Transaction confirmed successfully!")
    print_info("Fetching latest blockhash from network...")
    print_warning("This action will erase all data on the USB drive")
    print_error("Failed to connect to Solana network")
    console.print()

    time.sleep(1.5)

    # 6. Multi-step Process
    print_section_header("BUILD PROCESS EXAMPLE")

    steps = [
        "Downloading Alpine Linux rootfs",
        "Extracting filesystem",
        "Installing Solana tools",
        "Generating keypair",
        "Creating bootable image",
        "Flashing to USB device",
        "Verifying installation"
    ]

    for i, step in enumerate(steps, 1):
        print_step(i, len(steps), step)
        time.sleep(0.3)

    console.print()
    time.sleep(1.5)

    # 7. Menu Options
    print_section_header("MAIN MENU")

    console.print("[cyan]Select an option:[/cyan]\n")

    menu_items = [
        "1. Send SOL",
        "2. View Transaction History",
        "3. Request Airdrop (Devnet Only)",
        "4. Refresh Balance",
        "5. Network Status",
        "6. Unmount Wallet",
        "0. Exit"
    ]

    for item in menu_items:
        console.print(f"  {item}")

    console.print()

    # 8. Final Summary
    time.sleep(2)
    console.print()
    print_section_header("UI DEMO COMPLETE")

    console.print(Panel(
        "[bold white]This is the CURRENT UI of Coldstar Cold Wallet[/bold white]\n\n"
        "[dim]Features shown:[/dim]\n"
        "• ASCII art banner\n"
        "• Rich panels and tables\n"
        "• Color-coded status messages\n"
        "• Device listing\n"
        "• Wallet information display\n"
        "• Transaction previews\n"
        "• Step-by-step progress indicators\n"
        "• Menu-based navigation\n\n"
        "[yellow]Ready for UI improvements![/yellow]",
        title="[bold cyan]Current UI Overview[/bold cyan]",
        border_style="cyan"
    ))

    console.print()

if __name__ == "__main__":
    try:
        demo_ui()
    except KeyboardInterrupt:
        console.print("\n[dim]Demo interrupted[/dim]")
        sys.exit(0)
