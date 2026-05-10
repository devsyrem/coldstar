# macOS Quick Start Guide

## USB Drive Detection & Flashing on macOS

### Prerequisites
- macOS 10.10 or later
- Python 3.7+ installed
- A USB drive (for testing/flashing)

### Quick Test

1. **Test if USB detection works:**
   ```bash
   python3 test_macos_usb.py
   ```

2. **Manually test diskutil:**
   ```bash
   diskutil list
   ```
   You should see a list of all disks including any USB drives.

### Using the Cold Wallet System

#### Option 1: Basic Usage (No Root Required)
```bash
# Run the main application
python3 main.py

# The system will automatically:
# - Detect your USB drive
# - Mount it if needed
# - Set up the wallet structure
```

#### Option 2: Flash a USB Drive (Root Required)
```bash
# Build and flash
sudo python3 flash_usb.py --build

# Or just flash an existing image
sudo python3 flash_usb.py
```

### Common macOS Disk Paths

- **Main disk:** `/dev/disk0` (your Mac's internal drive - **DO NOT FLASH THIS!**)
- **USB drives:** `/dev/disk2`, `/dev/disk3`, etc.
- **Raw devices (faster):** `/dev/rdisk2`, `/dev/rdisk3`, etc.
- **Mount points:** `/Volumes/VOLUME_NAME`

### Finding Your USB Drive

```bash
# Before plugging in USB, run:
diskutil list

# Plug in your USB drive, then run again:
diskutil list

# The new disk that appears is your USB drive
# It will be labeled as (external, physical)
```

### Manual Operations

#### Unmount a USB Drive
```bash
diskutil unmount /Volumes/YOUR_USB_NAME
# or force unmount:
diskutil unmount force /Volumes/YOUR_USB_NAME
```

#### Mount a USB Drive
```bash
diskutil mount /dev/disk2s1
```

#### Eject a USB Drive Safely
```bash
diskutil eject /dev/disk2
```

#### Format a USB Drive (⚠️ ERASES DATA!)
```bash
# Format as FAT32 (Windows compatible)
diskutil eraseDisk FAT32 COLDSTAR MBR /dev/disk2

# Format as ExFAT (better for large files)
diskutil eraseDisk ExFAT COLDSTAR GPT /dev/disk2
```

### Troubleshooting

#### "Resource busy" Error
```bash
# Find what's using the disk:
lsof | grep /dev/disk2

# Force unmount:
diskutil unmount force /Volumes/YOUR_USB
```

#### Disk Not Appearing
```bash
# Refresh disk list:
diskutil list

# Check system log:
log show --predicate 'eventMessage contains "disk"' --last 5m
```

#### Permission Denied
```bash
# For flashing operations, use sudo:
sudo python3 flash_usb.py

# For basic detection, no sudo needed:
python3 main.py
```

### Performance Tips

1. **Use raw disk device for faster writes:**
   - Instead of `/dev/disk2`, use `/dev/rdisk2`
   - The code does this automatically!

2. **Larger block size:**
   - macOS dd uses lowercase: `bs=4m` (not `bs=4M`)
   - The code handles this automatically!

3. **Disable Spotlight on USB:**
   ```bash
   sudo mdutil -i off /Volumes/YOUR_USB
   ```

### Safety Tips

⚠️ **IMPORTANT - Before Flashing:**

1. **Verify the disk identifier:**
   ```bash
   diskutil info /dev/disk2
   ```
   Check that it says "external" and shows the correct size

2. **Double-check it's not your main drive:**
   - `/dev/disk0` is usually your Mac's internal drive
   - `/dev/disk1` might be a recovery partition
   - USB drives are typically `/dev/disk2` or higher

3. **Backup important data first!**
   - Flashing will **ERASE ALL DATA** on the drive

### Example Session

```bash
# 1. Test USB detection
$ python3 test_macos_usb.py
Current OS: Darwin
✓ Successfully imported USBManager
✓ Created USBManager instance
  - System: Darwin
  - is_macos: True
✓ Detection completed
  Found 1 USB device(s)

# 2. View detected devices
Detected Devices:
  Device 1:
    Path:       /dev/disk2
    Size:       32.0 GB
    Model:      SanDisk USB
    Mountpoint: /Volumes/COLDSTAR

# 3. Run the cold wallet system
$ python3 main.py
🔍 Detecting USB devices...
✓ Found 1 USB device(s)
✓ Selected device: /dev/disk2
✓ Using mounted volume: /Volumes/COLDSTAR

# Success!
```

### Getting Help

If you encounter issues:

1. Run the test script with verbose output
2. Check that diskutil is working: `diskutil list`
3. Verify Python version: `python3 --version`
4. Check system logs if drives aren't appearing

### Differences from Linux

| Task | Linux | macOS |
|------|-------|-------|
| List disks | `lsblk` | `diskutil list` |
| Disk info | `fdisk -l` | `diskutil info /dev/disk2` |
| Mount | `mount /dev/sdb1 /mnt` | `diskutil mount /dev/disk2s1` |
| Unmount | `umount /mnt` | `diskutil unmount /Volumes/USB` |
| Eject | `eject /dev/sdb` | `diskutil eject /dev/disk2` |
| Format | `mkfs.ext4 /dev/sdb1` | `diskutil eraseDisk` |
| Block size | `bs=4M` | `bs=4m` |

The Python code handles all these differences automatically! 🎉
