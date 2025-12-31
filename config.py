"""
Solana Cold Wallet USB Tool - Configuration

B - Love U 3000
"""

SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"

LAMPORTS_PER_SOL = 1_000_000_000

# Infrastructure fee configuration
INFRASTRUCTURE_FEE_PERCENTAGE = 0.01  # 1% fee
INFRASTRUCTURE_FEE_WALLET = "Cak1aAwxM2jTdu7AtdaHbqAc3Dfafts7KdsHNrtXN5rT"

WALLET_DIR = "/wallet"
INBOX_DIR = "/inbox"
OUTBOX_DIR = "/outbox"

ALPINE_MINIROOTFS_URL = "https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/x86_64/alpine-minirootfs-3.19.1-x86_64.tar.gz"

NETWORK_BLACKLIST_MODULES = [
    "e1000",
    "e1000e",
    "r8169",
    "iwlwifi",
    "ath9k",
    "ath10k",
    "rtl8xxxu",
    "mt7601u",
    "brcmfmac",
    "bcm43xx"
]

APP_VERSION = "1.0.0"
APP_NAME = "Solana Cold Wallet USB Tool"
