# Solana Cold Wallet USB Tool

## Overview
A Python-based terminal application for creating and managing Solana cold wallets on USB drives with offline transaction signing capabilities.

## Project State: COMPLETE
All core functionality implemented and tested with Devnet RPC.

## Architecture

### Core Files
- `main.py` - Main CLI entry point with menu system
- `config.py` - Configuration settings (RPC URL, constants)
- `src/ui.py` - Terminal UI components using Rich library
- `src/wallet.py` - Wallet/keypair generation and management
- `src/network.py` - Solana RPC communication
- `src/transaction.py` - Transaction creation, signing, serialization
- `src/usb.py` - USB device detection and mounting
- `src/iso_builder.py` - Alpine Linux rootfs builder for cold wallet USB

### Key Features
1. USB device detection and flashing
2. Ed25519 keypair generation using solders
3. SOL transfer transaction creation
4. Offline transaction signing
5. Transaction broadcasting to Solana network
6. Devnet airdrop requests

### Security Features
- Network drivers blacklisted in generated cold wallet OS
- iptables DROP rules applied on boot
- Network verification script included
- Private keys stored locally (keypair.json)

## How to Run
```bash
# Standard usage
python main.py

# For USB operations (requires root)
sudo python main.py
```

## Network Configuration
Currently configured for Devnet. To switch networks, edit `config.py`:
```python
SOLANA_RPC_URL = "https://api.devnet.solana.com"  # Current
# SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"  # For production
```

## Dependencies
- solana, solders - Solana SDK
- pynacl - Ed25519 cryptography
- rich - Terminal UI
- questionary - Interactive prompts
- httpx - HTTP client

## Directory Structure
```
local_wallet/
  keypair.json       # Private key (SECURE!)
  pubkey.txt         # Public key
  transactions/      # Transaction files
```

## Recent Changes
- 2024-12-23: Initial implementation complete
- Enhanced network isolation in ISO builder
- Added iptables lockdown and network verification scripts
