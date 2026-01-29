"""
ISO Builder - Create bootable Alpine Linux USB with Solana signing tools

B - Love U 3000
"""

import subprocess
import sys
import os
import shutil
import tempfile
import json
import platform
from pathlib import Path
from typing import Optional, Tuple

from src.ui import (
    print_success, print_error, print_info, print_warning,
    print_step, create_progress_bar, confirm_dangerous_action,
    print_wallet_info
)
from config import ALPINE_MINIROOTFS_URL, NETWORK_BLACKLIST_MODULES


class ISOBuilder:
    def __init__(self):
        self.work_dir: Optional[Path] = None
        self.rootfs_dir: Optional[Path] = None
        self.iso_path: Optional[Path] = None
        self.generated_pubkey: Optional[str] = None
        self.is_windows = platform.system() == 'Windows'
    
    def build_complete_iso(self, output_dir: str = "./output") -> Optional[Path]:
        """Build complete bootable ISO with transaction signing and keygen"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        with tempfile.TemporaryDirectory() as work_dir:
            self.work_dir = Path(work_dir)
            
            tarball = self.download_alpine_rootfs(work_dir)
            if not tarball:
                return None
            
            if not self.extract_rootfs(tarball):
                return None
            
            if not self.configure_offline_os():
                return None
            
            if not self._install_python_deps():
                return None
            
            iso_path = self._create_bootable_image(output_path)
            if iso_path:
                print_success(f"ISO created successfully: {iso_path}")
                return iso_path
            
            return None
    
    def download_alpine_rootfs(self, work_dir: str) -> Optional[Path]:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # On Windows, skip the Alpine download and use simplified approach
        if self.is_windows:
            print_step(1, 7, "Preparing wallet structure for Windows...")
            print_info("Using simplified wallet structure for Windows")
            # Create a dummy tarball path to satisfy the workflow
            tarball_path = self.work_dir / "wallet_structure.marker"
            tarball_path.touch()
            return tarball_path
        
        tarball_path = self.work_dir / "alpine-minirootfs.tar.gz"
        
        print_step(1, 7, "Downloading Alpine Linux minirootfs...")
        
        try:
            result = subprocess.run(
                ['wget', '-q', '--show-progress', '-O', str(tarball_path), ALPINE_MINIROOTFS_URL],
                capture_output=False,
                timeout=300
            )
            
            if result.returncode != 0:
                result = subprocess.run(
                    ['curl', '-L', '-o', str(tarball_path), ALPINE_MINIROOTFS_URL],
                    capture_output=True,
                    timeout=300
                )
            
            if tarball_path.exists():
                print_success("Alpine Linux rootfs downloaded")
                return tarball_path
            else:
                print_error("Failed to download Alpine rootfs")
                return None
                
        except subprocess.TimeoutExpired:
            print_error("Download timed out")
            return None
        except FileNotFoundError:
            print_error("wget/curl not found. Please install wget or curl.")
            return None
        except Exception as e:
            print_error(f"Download error: {e}")
            return None
    
    def extract_rootfs(self, tarball_path: Path) -> Optional[Path]:
        print_step(2, 7, "Extracting filesystem...")
        
        self.rootfs_dir = self.work_dir / "rootfs"
        self.rootfs_dir.mkdir(parents=True, exist_ok=True)
        
        # On Windows, just create the directory structure
        if self.is_windows:
            print_success("Creating wallet directory structure")
            return self.rootfs_dir
        
        try:
            result = subprocess.run(
                ['tar', '-xzf', str(tarball_path), '-C', str(self.rootfs_dir)],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                print_success("Filesystem extracted")
                return self.rootfs_dir
            else:
                print_error(f"Extraction failed: {result.stderr}")
                return None
                
        except Exception as e:
            print_error(f"Extraction error: {e}")
            return None
    
    def configure_offline_os(self) -> bool:
        if not self.rootfs_dir:
            print_error("No rootfs directory set")
            return False
        
        print_step(3, 7, "Configuring offline OS...")
        
        try:
            wallet_dir = self.rootfs_dir / "wallet"
            inbox_dir = self.rootfs_dir / "inbox"
            outbox_dir = self.rootfs_dir / "outbox"
            
            for d in [wallet_dir, inbox_dir, outbox_dir]:
                d.mkdir(parents=True, exist_ok=True)
            
            modprobe_dir = self.rootfs_dir / "etc" / "modprobe.d"
            modprobe_dir.mkdir(parents=True, exist_ok=True)
            blacklist_conf = modprobe_dir / "blacklist-network.conf"
            
            with open(blacklist_conf, 'w') as f:
                f.write("# Network modules blacklisted for offline cold wallet\n")
                f.write("# Ethernet drivers\n")
                for module in NETWORK_BLACKLIST_MODULES:
                    f.write(f"blacklist {module}\n")
                f.write("# Additional wireless drivers\n")
                f.write("blacklist cfg80211\n")
                f.write("blacklist mac80211\n")
                f.write("blacklist rfkill\n")
                f.write("blacklist bluetooth\n")
                f.write("blacklist btusb\n")
                f.write("# USB network adapters\n")
                f.write("blacklist usbnet\n")
                f.write("blacklist cdc_ether\n")
                f.write("blacklist rndis_host\n")
                f.write("blacklist ax88179_178a\n")
            
            print_success("Network drivers blacklisted")
            
            self._disable_network_services()
            self._create_network_lockdown_script()
            self._create_signing_script()
            self._create_first_boot_keygen()
            self._create_boot_profile()
            
            print_success("Offline OS configured")
            return True
            
        except Exception as e:
            print_error(f"Configuration error: {e}")
            return False
    
    def _install_python_deps(self) -> bool:
        """Create a setup script for installing Python deps on first boot"""
        print_step(4, 7, "Configuring Python environment...")
        
        setup_script = self.rootfs_dir / "etc" / "local.d" / "setup-python.start"
        setup_script.parent.mkdir(parents=True, exist_ok=True)
        
        setup_content = '''#!/bin/sh
# Install Python and Solana dependencies on first boot
if [ ! -f /var/lib/.python-setup-done ]; then
    echo "Setting up Python environment..."
    apk update 2>/dev/null || true
    apk add python3 py3-pip py3-pynacl 2>/dev/null || true
    pip3 install solders solana pynacl --break-system-packages 2>/dev/null || true
    touch /var/lib/.python-setup-done
    echo "Python setup complete"
fi
'''
        
        with open(setup_script, 'w') as f:
            f.write(setup_content)
        os.chmod(setup_script, 0o755)
        
        # Copy the SecureWalletHandler module
        self._copy_secure_memory_module()
        
        print_success("Python environment configured")
        return True

    def _copy_secure_memory_module(self):
        """Copy the secure memory module to the offline OS"""
        src_path = Path("temp_coldstar/src/secure_memory.py")
        dest_path = self.rootfs_dir / "usr" / "local" / "bin" / "secure_memory.py"
        
        if src_path.exists():
            shutil.copy2(src_path, dest_path)
            print_info("Secure memory module copied to offline OS")
        else:
            print_warning(f"Could not find secure_memory.py at {src_path}")

    
    def _disable_network_services(self):
        init_dir = self.rootfs_dir / "etc" / "init.d"
        init_dir.mkdir(parents=True, exist_ok=True)
        
        rclocal = self.rootfs_dir / "etc" / "local.d" / "disable-network.start"
        rclocal.parent.mkdir(parents=True, exist_ok=True)
        
        network_lockdown = '''#!/bin/sh
# Ensure no network interfaces come up
for iface in $(ls /sys/class/net/ 2>/dev/null | grep -v lo); do
    ip link set "$iface" down 2>/dev/null
done

# Drop all network traffic via iptables if available
if command -v iptables >/dev/null 2>&1; then
    iptables -P INPUT DROP 2>/dev/null
    iptables -P OUTPUT DROP 2>/dev/null
    iptables -P FORWARD DROP 2>/dev/null
fi

# Kill any networking daemons that might have started
for proc in dhcpcd udhcpc wpa_supplicant NetworkManager; do
    pkill -9 "$proc" 2>/dev/null
done
'''
        
        with open(rclocal, 'w') as f:
            f.write(network_lockdown)
        os.chmod(rclocal, 0o755)
        
        interfaces_file = self.rootfs_dir / "etc" / "network" / "interfaces"
        interfaces_file.parent.mkdir(parents=True, exist_ok=True)
        with open(interfaces_file, 'w') as f:
            f.write("# Network interfaces disabled for cold wallet security\n")
            f.write("auto lo\n")
            f.write("iface lo inet loopback\n")
        
        print_success("Network services disabled")
    
    def _create_network_lockdown_script(self):
        script_path = self.rootfs_dir / "usr" / "local" / "bin" / "verify_offline.sh"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        
        script_content = '''#!/bin/sh
# Verify system is truly offline

echo "NETWORK STATUS CHECK"
echo "===================="

ONLINE=0

for iface in $(ls /sys/class/net/ 2>/dev/null); do
    if [ "$iface" != "lo" ]; then
        state=$(cat /sys/class/net/$iface/operstate 2>/dev/null)
        if [ "$state" = "up" ]; then
            echo "WARNING: Interface $iface is UP!"
            ONLINE=1
        fi
    fi
done

if command -v ping >/dev/null 2>&1; then
    if ping -c 1 -W 1 8.8.8.8 >/dev/null 2>&1; then
        echo "WARNING: Network connectivity detected!"
        ONLINE=1
    fi
fi

if [ $ONLINE -eq 0 ]; then
    echo "VERIFIED: System is OFFLINE"
    echo "Safe for transaction signing."
else
    echo ""
    echo "WARNING: NETWORK ACCESS DETECTED!"
    echo "Do NOT sign transactions on this system!"
fi
'''
        
        with open(script_path, 'w') as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)
    
    def _create_signing_script(self):
        script_dir = self.rootfs_dir / "usr" / "local" / "bin"
        script_dir.mkdir(parents=True, exist_ok=True)
        
        sign_script = script_dir / "sign_tx.sh"
        
        script_content = '''#!/bin/sh
# Solana Offline Transaction Signing Script
# B - Love U 3000

WALLET_DIR="/wallet"
INBOX_DIR="/inbox"
OUTBOX_DIR="/outbox"
KEYPAIR_FILE="$WALLET_DIR/keypair.json"
PUBKEY_FILE="$WALLET_DIR/pubkey.txt"

echo "=============================================="
echo "    SOLANA OFFLINE TRANSACTION SIGNER"
echo "=============================================="
echo ""

if [ ! -f "$KEYPAIR_FILE" ]; then
    echo "ERROR: No wallet found at $KEYPAIR_FILE"
    echo "Please initialize wallet first."
    exit 1
fi

if [ -f "$PUBKEY_FILE" ]; then
    echo "Wallet Public Key:"
    cat "$PUBKEY_FILE"
    echo ""
fi

UNSIGNED_TX=$(find "$INBOX_DIR" -name "*.json" -type f | head -1)

if [ -z "$UNSIGNED_TX" ]; then
    echo "No unsigned transaction found in $INBOX_DIR"
    echo ""
    echo "Instructions:"
    echo "1. Copy unsigned transaction file to $INBOX_DIR"
    echo "2. Run this script again"
    exit 0
fi

echo "Found unsigned transaction: $UNSIGNED_TX"
echo ""
echo "WARNING: You are about to sign this transaction."
echo "Review the transaction details carefully."
echo ""
read -p "Type 'SIGN' to confirm: " confirm

if [ "$confirm" != "SIGN" ]; then
    echo "Signing cancelled."
    exit 0
fi

BASENAME=$(basename "$UNSIGNED_TX" .json)
SIGNED_TX="$OUTBOX_DIR/${BASENAME}_signed.json"

python3 /usr/local/bin/offline_sign.py "$UNSIGNED_TX" "$KEYPAIR_FILE" "$SIGNED_TX"

if [ $? -eq 0 ]; then
    echo ""
    echo "SUCCESS: Transaction signed!"
    echo "Signed transaction saved to: $SIGNED_TX"
    echo ""
    echo "Next steps:"
    echo "1. Copy $SIGNED_TX to your online host"
    echo "2. Broadcast the transaction"
else
    echo "ERROR: Signing failed"
    exit 1
fi
'''
        
        with open(sign_script, 'w') as f:
            f.write(script_content)
        
        os.chmod(sign_script, 0o755)
        
        python_sign_script = script_dir / "offline_sign.py"
        
        python_content = '''#!/usr/bin/env python3
"""Offline transaction signing script for cold wallet"""

import sys
import json
import base64
import getpass
import gc

# Add local bin to path to find secure_memory
sys.path.append("/usr/local/bin")

def main():
    if len(sys.argv) != 4:
        print("Usage: offline_sign.py <unsigned_tx> <keypair> <output>")
        sys.exit(1)
    
    unsigned_path = sys.argv[1]
    keypair_path = sys.argv[2]
    output_path = sys.argv[3]
    
    try:
        from solders.keypair import Keypair
        from solders.transaction import Transaction
        
        # Try importing secure memory handler
        try:
            from secure_memory import SecureWalletHandler
        except ImportError:
            print("WARNING: secure_memory module not found. Encryption disabled.")
            SecureWalletHandler = None
        
        with open(keypair_path, 'r') as f:
            wallet_data = json.load(f)
            
        keypair = None
        
        # Handle legacy unencrypted format (list of ints)
        if isinstance(wallet_data, list):
            print("WARNING: Using legacy UNENCRYPTED wallet format.")
            keypair = Keypair.from_bytes(bytes(wallet_data))
        else:
            # Handle encrypted format
            if SecureWalletHandler:
                print("Wallet is encrypted.")
                password = getpass.getpass("Enter wallet password: ")
                keypair = SecureWalletHandler.decrypt_keypair(wallet_data, password)
                if not keypair:
                    print("ERROR: Invalid password or corrupted wallet.")
                    sys.exit(1)
            else:
                print("ERROR: Encrypted wallet found but secure_memory module missing.")
                sys.exit(1)
        
        with open(unsigned_path, 'r') as f:
            tx_data = json.load(f)
        
        tx_bytes = base64.b64decode(tx_data['data'])
        tx = Transaction.from_bytes(tx_bytes)
        
        tx.sign([keypair], tx.message.recent_blockhash)
        
        # Clear keypair from memory immediately after signing
        del keypair
        gc.collect()
        
        signed_data = {
            "type": "signed_transaction",
            "version": "1.0",
            "data": base64.b64encode(bytes(tx)).decode('utf-8')
        }
        
        with open(output_path, 'w') as f:
            json.dump(signed_data, f, indent=2)
        
        print("Transaction signed successfully")
        
    except ImportError:
        print("ERROR: solders library not installed")
        print("Install with: pip install solders")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
        
        with open(python_sign_script, 'w') as f:
            f.write(python_content)
        
        os.chmod(python_sign_script, 0o755)
        print_success("Signing scripts created")
    
    def _create_boot_profile(self):
        profile_path = self.rootfs_dir / "etc" / "profile.d" / "wallet-welcome.sh"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        
        profile_content = '''#!/bin/sh
# Wallet boot message
# B - Love U 3000

clear
echo ""
echo "=============================================="
echo "     SOLANA COLD WALLET - OFFLINE MODE"
echo "=============================================="
echo ""

if [ -f /wallet/pubkey.txt ]; then
    echo "Wallet Public Key:"
    echo "--------------------------------------------"
    cat /wallet/pubkey.txt
    echo ""
    echo "--------------------------------------------"
else
    echo "Wallet not yet initialized."
    echo "Run: python3 /usr/local/bin/init_wallet.py"
    echo "to generate your wallet on this air-gapped device."
fi

echo ""
echo "SECURITY: This device has NO network access."
echo ""
echo "Commands:"
echo "  sign_tx.sh    - Sign a transaction"
echo ""
echo "Directories:"
echo "  /wallet       - Wallet keypair storage"
echo "  /inbox        - Place unsigned transactions here"
echo "  /outbox       - Signed transactions appear here"
echo ""
echo "=============================================="
echo ""
'''
        
        with open(profile_path, 'w') as f:
            f.write(profile_content)
        
        os.chmod(profile_path, 0o755)
        print_success("Boot profile created")
    
    def _create_first_boot_keygen(self):
        script_dir = self.rootfs_dir / "usr" / "local" / "bin"
        script_dir.mkdir(parents=True, exist_ok=True)
        
        keygen_script = script_dir / "init_wallet.py"
        
        keygen_content = '''#!/usr/bin/env python3
"""First-boot wallet initialization - generates keypair on air-gapped device"""

import os
import sys
import json
import getpass
import gc

# Add local bin to path to find secure_memory
sys.path.append("/usr/local/bin")

WALLET_DIR = "/wallet"
KEYPAIR_FILE = f"{WALLET_DIR}/keypair.json"
PUBKEY_FILE = f"{WALLET_DIR}/pubkey.txt"

def main():
    if os.path.exists(KEYPAIR_FILE):
        print("Wallet already initialized.")
        with open(PUBKEY_FILE, 'r') as f:
            print(f"Public Key: {f.read().strip()}")
        return
    
    print("=" * 50)
    print("  GENERATING NEW WALLET ON AIR-GAPPED DEVICE")
    print("=" * 50)
    print()
    print("SECURITY: This private key is being generated")
    print("directly on this offline device and has NEVER")
    print("touched any networked computer.")
    print()
    
    try:
        from solders.keypair import Keypair
        
        # Try importing secure memory handler
        try:
            from secure_memory import SecureWalletHandler
        except ImportError:
            print("ERROR: secure_memory module not found. Cannot encrypt wallet.")
            sys.exit(1)
        
        print("You must set a password to encrypt your wallet.")
        password = getpass.getpass("Set wallet password: ")
        confirm = getpass.getpass("Confirm password:    ")
        
        if password != confirm:
            print("ERROR: Passwords do not match!")
            sys.exit(1)
            
        if not password:
            print("ERROR: Password cannot be empty.")
            sys.exit(1)
        
        print("Generating keypair...")
        keypair = Keypair()
        public_key = str(keypair.pubkey())
        
        os.makedirs(WALLET_DIR, exist_ok=True)
        
        print("Encrypting wallet...")
        encrypted_data = SecureWalletHandler.encrypt_keypair(keypair, password)
        
        with open(KEYPAIR_FILE, 'w') as f:
            json.dump(encrypted_data, f)
        
        # Clear keypair from memory immediately
        del keypair
        gc.collect()
        
        os.chmod(KEYPAIR_FILE, 0o600)
        
        with open(PUBKEY_FILE, 'w') as f:
            f.write(public_key)
        
        print("=" * 50)
        print("  WALLET GENERATED & ENCRYPTED SUCCESSFULLY")
        print("=" * 50)
        print()
        print("YOUR PUBLIC KEY (WALLET ADDRESS):")
        print("-" * 50)
        print(public_key)
        print("-" * 50)
        print()
        print("IMPORTANT: Write down or photograph this address!")
        print("You will need it to receive SOL on this wallet.")
        print()
        print("The private key is stored securely (ENCRYPTED)")
        print("on this device and will NEVER leave this system.")
        print("=" * 50)
        
    except ImportError:
        print("ERROR: solders library not available")
        print("The cold wallet OS may be incomplete.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
        
        with open(keygen_script, 'w') as f:
            f.write(keygen_content)
        os.chmod(keygen_script, 0o755)
        
        first_boot_script = self.rootfs_dir / "etc" / "local.d" / "init-wallet.start"
        first_boot_script.parent.mkdir(parents=True, exist_ok=True)
        
        boot_init_content = '''#!/bin/sh
# First boot wallet initialization
if [ ! -f /wallet/keypair.json ]; then
    python3 /usr/local/bin/init_wallet.py
fi
'''
        
        with open(first_boot_script, 'w') as f:
            f.write(boot_init_content)
        os.chmod(first_boot_script, 0o755)
        
        print_success("First-boot keygen script created")
        print_info("Wallet will be generated on first boot of air-gapped device")
    
    def _create_bootable_image(self, output_dir: Path) -> Optional[Path]:
        """Create a bootable disk image"""
        print_step(5, 7, "Creating bootable image...")
        
        image_path = output_dir / "solana-cold-wallet.img"
        
        try:
            print_info("Creating 512MB disk image...")
            subprocess.run(
                ['dd', 'if=/dev/zero', f'of={image_path}', 'bs=1M', 'count=512'],
                capture_output=True,
                timeout=120
            )
            
            print_info("Setting up partition table...")
            subprocess.run(['parted', '-s', str(image_path), 'mklabel', 'msdos'], capture_output=True)
            subprocess.run(['parted', '-s', str(image_path), 'mkpart', 'primary', 'ext4', '1MiB', '100%'], capture_output=True)
            subprocess.run(['parted', '-s', str(image_path), 'set', '1', 'boot', 'on'], capture_output=True)
            
            loop_result = subprocess.run(
                ['losetup', '--find', '--show', '-P', str(image_path)],
                capture_output=True,
                text=True
            )
            
            if loop_result.returncode != 0:
                print_warning("Loop device setup requires root. Creating archive instead.")
                return self._create_archive_image(output_dir)
            
            loop_device = loop_result.stdout.strip()
            partition = f"{loop_device}p1"
            
            print_info("Formatting partition...")
            subprocess.run(['mkfs.ext4', '-F', partition], capture_output=True, timeout=60)
            
            mount_point = self.work_dir / "mnt"
            mount_point.mkdir(exist_ok=True)
            
            subprocess.run(['mount', partition, str(mount_point)], capture_output=True)
            
            print_info("Copying filesystem...")
            subprocess.run(
                ['cp', '-a', f'{self.rootfs_dir}/.', str(mount_point)],
                capture_output=True,
                timeout=300
            )
            
            subprocess.run(['umount', str(mount_point)], capture_output=True)
            subprocess.run(['losetup', '-d', loop_device], capture_output=True)
            
            print_success(f"Bootable image created: {image_path}")
            self.iso_path = image_path
            return image_path
            
        except subprocess.TimeoutExpired:
            print_warning("Image creation timed out, creating archive instead")
            return self._create_archive_image(output_dir)
        except Exception as e:
            print_warning(f"Image creation failed: {e}, creating archive instead")
            return self._create_archive_image(output_dir)
    
    def _create_archive_image(self, output_dir: Path) -> Optional[Path]:
        """Fallback: create a tar.gz archive of the filesystem"""
        print_step(5, 7, "Creating portable filesystem archive...")
        
        archive_path = output_dir / "solana-cold-wallet.tar.gz"
        
        try:
            result = subprocess.run(
                ['tar', '-czf', str(archive_path), '-C', str(self.rootfs_dir), '.'],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                print_success(f"Filesystem archive created: {archive_path}")
                self.iso_path = archive_path
                return archive_path
            else:
                print_error(f"Failed to create archive: {result.stderr}")
                return None
                
        except Exception as e:
            print_error(f"Archive creation failed: {e}")
            return None
    
    def get_generated_pubkey(self) -> Optional[str]:
        return self.generated_pubkey
    
    def build_iso(self, output_path: str = None) -> Optional[Path]:
        """Legacy method - use build_complete_iso instead"""
        return self.build_complete_iso(output_path or "./output")
    
    def flash_to_usb(self, device_path: str, image_path: str = None) -> bool:
        """Flash wallet structure to USB - Windows uses direct copy, Linux uses dd"""
        
        # On Windows, device_path will be like \\\\.\\PHYSICALDRIVE1, but we need the drive letter
        if self.is_windows:
            return self._flash_to_usb_windows(device_path, image_path)
        else:
            return self._flash_to_usb_linux(device_path, image_path)
    
    def _generate_wallet_on_usb(self, mount_point: str) -> bool:
        """Generate keypair and wallet on the USB drive (Step 7)"""
        print_step(7, 7, "Generating keypair and wallet on USB...")
        
        try:
            from solders.keypair import Keypair
            from src.secure_memory import SecureWalletHandler
            from src.ui import get_password_input
            
            wallet_dir = Path(mount_point) / "wallet"
            wallet_dir.mkdir(parents=True, exist_ok=True)
            
            keypair_path = wallet_dir / "keypair.json"
            pubkey_path = wallet_dir / "pubkey.txt"
            
            # Check if wallet already exists
            if keypair_path.exists() and pubkey_path.exists():
                print_info("Wallet already exists on this USB drive")
                with open(pubkey_path, 'r') as f:
                    existing_pubkey = f.read().strip()
                print_info(f"Existing Public Key: {existing_pubkey}")
                
                from src.ui import select_menu_option
                overwrite_choice = select_menu_option(
                    ["Keep existing wallet", "Create new wallet (overwrites)"],
                    "What would you like to do?"
                )
                if not overwrite_choice or "Keep" in overwrite_choice:
                    print_info("Using existing wallet")
                    self.generated_pubkey = existing_pubkey
                    return True
            
            print_info("Generating new Solana keypair...")
            keypair = Keypair()
            public_key = str(keypair.pubkey())
            
            print_success(f"Generated keypair: {public_key[:8]}...{public_key[-8:]}")
            
            # Get password for encryption
            print_info("")
            print_info("Your wallet will be encrypted with a password.")
            print_warning("IMPORTANT: Remember this password - you cannot recover funds without it!")
            password = get_password_input("Set wallet password:")
            confirm_password = get_password_input("Confirm password:")
            
            if password != confirm_password:
                print_error("Passwords do not match!")
                return False
            
            if not password:
                print_error("Password cannot be empty!")
                return False
            
            print_info("Encrypting wallet...")
            encrypted_data = SecureWalletHandler.encrypt_keypair(keypair, password)
            
            # Save encrypted keypair
            with open(keypair_path, 'w') as f:
                json.dump(encrypted_data, f, indent=2)
            
            # Save public key
            with open(pubkey_path, 'w') as f:
                f.write(public_key)
            
            # Set secure permissions if on Unix
            if not self.is_windows:
                os.chmod(keypair_path, 0o600)
                os.chmod(pubkey_path, 0o644)
            
            # Clear keypair from memory
            del keypair
            import gc
            gc.collect()
            
            print_success("✓ Wallet created and encrypted successfully!")
            print_info("")
            print_info("=" * 60)
            print_success("YOUR WALLET PUBLIC KEY (ADDRESS):")
            print_info(public_key)
            print_info("=" * 60)
            print_info("")
            print_warning("Write down or photograph this address!")
            print_warning("You need this to receive SOL on this wallet.")
            print_info("")
            
            # Store the generated pubkey for later reference
            self.generated_pubkey = public_key
            
            return True
            
        except ImportError as e:
            print_error(f"Required modules not available: {e}")
            print_info("Make sure solders and secure_memory are installed")
            return False
        except Exception as e:
            print_error(f"Wallet generation failed: {e}")
            import traceback
            if "--debug" in sys.argv:
                traceback.print_exc()
            return False
    
    def _flash_to_usb_windows(self, device_path: str, image_path: str = None) -> bool:
        """Flash on Windows by copying wallet structure to drive"""
        print_step(6, 7, "Setting up wallet on USB drive...")
        
        # For Windows, we need to get the mount point (drive letter)
        # The device_path might be like \\\\.\\PHYSICALDRIVE1, but we need D:\\ or similar
        # We'll look for the drive letter in the detected devices
        
        try:
            # Get drive letter from PowerShell
            ps_command = f"""
            $drive = Get-WmiObject Win32_DiskDrive | Where-Object {{$_.DeviceID -eq '{device_path}'}}
            $partitions = Get-WmiObject -Query "ASSOCIATORS OF {{Win32_DiskDrive.DeviceID='$($drive.DeviceID)'}} WHERE AssocClass=Win32_DiskDriveToDiskPartition"
            foreach ($partition in $partitions) {{
                $logical = Get-WmiObject -Query "ASSOCIATORS OF {{Win32_DiskPartition.DeviceID='$($partition.DeviceID)'}} WHERE AssocClass=Win32_LogicalDiskToPartition"
                foreach ($vol in $logical) {{
                    Write-Output $vol.DeviceID
                }}
            }}
            """
            
            result = subprocess.run(
                ['powershell', '-Command', ps_command],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                drive_letter = result.stdout.strip().split()[0]  # Get first drive letter
                mount_point = drive_letter + '\\\\'
                
                print_info(f"Using drive: {mount_point}")
                
                # Create wallet structure on the USB drive
                wallet_dir = Path(mount_point) / "wallet"
                inbox_dir = Path(mount_point) / "inbox"
                outbox_dir = Path(mount_point) / "outbox"
                
                for d in [wallet_dir, inbox_dir, outbox_dir]:
                    d.mkdir(parents=True, exist_ok=True)
                
                # Copy README instructions
                readme_content = """SOLANA COLD WALLET USB DRIVE
================================

This USB drive contains your Solana cold wallet structure.

SECURITY WARNING:
- Keep this drive OFFLINE and SECURE
- Never plug into internet-connected computers for signing
- The private key should NEVER leave this device

Directory Structure:
--------------------
wallet/  - Contains keypair.json and pubkey.txt
inbox/   - Place unsigned transactions here for signing
outbox/  - Signed transactions will be placed here

Usage:
------
1. Your wallet has been pre-generated and is ready to use
2. Copy unsigned transactions to inbox/
3. Use offline signing tools to sign transactions
4. Retrieve signed transactions from outbox/

For more information, see the project documentation.
"""
                
                readme_path = Path(mount_point) / "README.txt"
                with open(readme_path, 'w') as f:
                    f.write(readme_content)
                
                print_success(f"Wallet structure created on {mount_point}")
                print_info("Directories created: wallet/, inbox/, outbox/")
                
                # Step 7: Generate keypair and wallet on the USB drive
                if not self._generate_wallet_on_usb(mount_point):
                    print_warning("Wallet structure created, but keypair generation failed")
                    print_info("You can generate the wallet manually later")
                    return True  # Still return True since structure is created
                
                return True
            else:
                print_error("Could not determine drive letter")
                print_info("Please manually note your USB drive letter (e.g., D:\\\\)")
                return False
                
        except Exception as e:
            print_error(f"Flash error: {e}")
            return False
    
    def _flash_to_usb_linux(self, device_path: str, image_path: str = None) -> bool:
        """Flash on Linux using dd or mount/copy"""
        image = Path(image_path) if image_path else self.iso_path
        
        if not image or not image.exists():
            print_error("No image file to flash")
            return False
        
        print_step(6, 7, f"Flashing to {device_path}...")
        print_warning(f"This will ERASE ALL DATA on {device_path}")
        
        try:
            mount_point = None
            
            if str(image).endswith('.img') or str(image).endswith('.iso'):
                result = subprocess.run(
                    ['dd', f'if={image}', f'of={device_path}', 'bs=4M', 'status=progress', 'oflag=sync'],
                    capture_output=False,
                    timeout=600
                )
            else:
                print_info("Formatting USB device...")
                subprocess.run(['mkfs.ext4', '-F', device_path], capture_output=True, timeout=60)
                
                mount_point = f"/tmp/usb_flash_{os.getpid()}"
                os.makedirs(mount_point, exist_ok=True)
                
                subprocess.run(['mount', device_path, mount_point], capture_output=True, timeout=30)
                
                result = subprocess.run(
                    ['tar', '-xzf', str(image), '-C', mount_point],
                    capture_output=True,
                    timeout=300
                )
            
            if result.returncode == 0:
                # Step 7: Generate wallet on USB if we have a mount point
                if mount_point:
                    if not self._generate_wallet_on_usb(mount_point):
                        print_warning("Wallet structure created, but keypair generation failed")
                        print_info("You can generate the wallet manually later")
                    subprocess.run(['umount', mount_point], capture_output=True, timeout=30)
                
                print_success("USB flash completed successfully!")
                return True
            else:
                if mount_point:
                    subprocess.run(['umount', mount_point], capture_output=True, timeout=30)
                print_error("Flash operation failed")
                return False
                
        except subprocess.TimeoutExpired:
            print_error("Flash operation timed out")
            return False
        except PermissionError:
            print_error("Permission denied. Run with sudo.")
            return False
        except Exception as e:
            print_error(f"Flash error: {e}")
            return False
    
    def cleanup(self):
        print_step(7, 7, "Cleaning up temporary files...")
        
        if self.work_dir and self.work_dir.exists():
            try:
                if self.rootfs_dir and self.rootfs_dir.exists():
                    shutil.rmtree(self.rootfs_dir, ignore_errors=True)
                
                tarball = self.work_dir / "alpine-minirootfs.tar.gz"
                if tarball.exists():
                    tarball.unlink()
                
                print_success("Cleanup completed")
            except Exception as e:
                print_warning(f"Cleanup warning: {e}")
    
    def get_iso_path(self) -> Optional[Path]:
        return self.iso_path
