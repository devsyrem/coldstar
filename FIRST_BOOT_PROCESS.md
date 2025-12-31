# First Instance Boot Process

## Overview

The **First Instance Boot Process** is an intelligent file integrity system that automatically detects when a USB cold wallet is plugged into a machine and ensures all critical wallet files are present and valid.

**This is NOT a restoration function** - it's a smart boot detection mechanism that happens seamlessly every time you plug in your USB drive.

## How It Works

### 1. Boot Instance Detection

Every time you plug in your USB drive:
- A unique boot instance ID is generated based on:
  - Machine hostname
  - Process ID
  - Current timestamp
  
- This ID is compared with the last boot marker stored on the USB
- If different (or missing), it's considered a "first boot" on this machine/session

### 2. Automatic File Verification

The system checks critical wallet files:
- `wallet/keypair.json` - Your encrypted private key
- `wallet/pubkey.txt` - Your public key

For each file, it verifies:
- ✅ File exists
- ✅ File is not empty (not corrupted)
- ✅ File has valid content

### 3. Intelligent Restoration

**Only if files are missing or corrupted:**
- Restores from backup stored in `.coldstar/backup/`
- Reports exactly which files were restored
- Creates backups of valid files for future protection

**If files are already valid:**
- No restoration occurs
- Updates backup if current file is newer
- Simply verifies integrity and continues

## Storage Structure

Your USB drive will have this structure:

```
USB Drive (E:\ or /mount/point)
├── wallet/
│   ├── keypair.json          # Your encrypted private key
│   └── pubkey.txt             # Your public address
├── inbox/                     # Unsigned transactions
├── outbox/                    # Signed transactions
└── .coldstar/                 # Hidden system directory
    ├── last_boot_id           # Boot instance tracker
    └── backup/                # Automatic backups
        ├── keypair.json       # Backup of encrypted key
        └── pubkey.txt         # Backup of public key
```

## When It Runs

The first instance boot process runs automatically:

1. **Every time you plug in the USB** - Detects new machine/session
2. **On every mount operation** - Even if already plugged in
3. **Transparent to the user** - No manual intervention needed

## What You'll See

### Normal Boot (No Restoration Needed)
```
Using drive: E:\
🔄 First instance boot detected on this machine...
Boot instance verified - checking wallet integrity...
✓ First boot process completed - no restoration needed
```

### Boot with File Restoration
```
Using drive: E:\
🔄 First instance boot detected on this machine...
⚠ Missing: keypair.json
✓ Restored keypair.json from backup
⚠ Missing: pubkey.txt
✓ Restored pubkey.txt from backup
✓ First boot process completed - 2 file(s) restored
```

### Subsequent Boots (Same Machine)
```
Using drive: E:\
Boot instance verified - checking wallet integrity...
✓ Created backup: keypair.json
✓ Integrity check completed - no restoration needed
```

## Security Features

### ✅ Backup Protection
- Backups are stored in hidden `.coldstar` directory
- Only created from valid source files
- Automatically updated when files change

### ✅ Corruption Detection
- Catches empty files (0 bytes)
- Prevents using corrupted wallets
- Immediate notification if backup is needed but missing

### ✅ No Data Loss
- Original files never overwritten unless corrupted
- Backups only created from verified valid files
- Clear reporting of all restoration actions

### ✅ Machine-Specific Tracking
- Each machine/session gets unique boot ID
- Prevents unnecessary restoration on same session
- Detects when USB is moved between machines

## Use Cases

### 1. Moving USB Between Computers
**Scenario:** You move your cold wallet USB from Computer A to Computer B

**Result:**
- First boot detected on Computer B
- Files verified automatically
- Any missing files restored from backup
- Wallet ready to use immediately

### 2. Accidental File Deletion
**Scenario:** Critical files accidentally deleted while USB mounted

**Result:**
- Next time you plug in USB: restoration triggered
- Files restored from `.coldstar/backup/`
- Wallet functionality preserved

### 3. File Corruption
**Scenario:** Power loss during write operation corrupts keypair.json

**Result:**
- System detects 0-byte file
- Automatically restores from backup
- You're warned about the corruption

### 4. Normal Daily Use
**Scenario:** You use the same USB on the same computer repeatedly

**Result:**
- First time: Creates backups
- Subsequent times: Quick integrity check only
- No unnecessary file operations

## Developer Integration

The first instance boot process is integrated into `USBManager.mount_device()`:

```python
# Automatically called after every successful mount
self.first_instance_boot_process(self.mount_point)
```

### Key Methods

```python
def first_instance_boot_process(self, mount_point: str = None) -> bool:
    """
    Main entry point - detects first boot and triggers restoration if needed
    Returns True on success
    """
    
def _check_and_restore_wallet_files(self, base_path: Path, backup_dir: Path) -> int:
    """
    Verifies critical files and restores if needed
    Returns number of files restored
    """
    
def _create_backup_if_needed(self, file_path: Path, backup_dir: Path):
    """
    Creates or updates backups of valid files
    """
```

## Technical Details

### Boot ID Generation
```python
import hashlib
import time
import platform

machine_id = f"{platform.node()}{os.getpid()}{time.time()}"
boot_id = hashlib.sha256(machine_id.encode()).hexdigest()[:16]
```

### File Validation
- Existence check: `file_path.exists()`
- Size check: `file_path.stat().st_size > 0`
- Backup comparison: `st_mtime` comparison

### Backup Strategy
- Automatic backup creation on first valid file detection
- Incremental updates when source files are modified
- Never overwrites valid files with backups unless source is corrupted

## Benefits

✅ **Zero User Intervention** - Everything happens automatically  
✅ **Protection Against Accidents** - Files can be recovered  
✅ **Cross-Machine Compatibility** - USB works on any machine  
✅ **Corruption Detection** - Catches file system errors  
✅ **Performance Optimized** - Only runs when needed  
✅ **Security Maintained** - Backups are encrypted same as originals  

## Frequently Asked Questions

**Q: Does this run on every USB mount?**  
A: Yes, but it's extremely fast if files are valid - just a quick integrity check.

**Q: Will it restore old files over new ones?**  
A: No! It only restores if the current file is missing or corrupted (0 bytes).

**Q: Where are backups stored?**  
A: In `.coldstar/backup/` directory on your USB drive itself.

**Q: Can I disable this feature?**  
A: It's built into the mount process, but you can delete `.coldstar/` if needed. However, this removes your safety net.

**Q: What if both the file AND backup are corrupted?**  
A: The system will notify you that restoration failed and no backup is available. You'd need to restore from your offline backup.

**Q: Does this work on both Windows and Linux?**  
A: Yes! It's platform-agnostic and uses Python's pathlib for cross-platform compatibility.

---

**B - Love U 3000** ❤️
