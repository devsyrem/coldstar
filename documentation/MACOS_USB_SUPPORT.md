# macOS USB Support

## Overview
The USB detection and management system now fully supports macOS using the native `diskutil` command-line tool.

## What Was Changed

### 1. **src/usb.py** - Core USB Management
- Added `is_macos` flag detection (Darwin system)
- Implemented `_detect_macos()` method using `diskutil list -plist external`
- Added `_detect_macos_fallback()` for systems without plistlib
- Updated `mount_device()` to use `diskutil mount` on macOS
- Updated `unmount_device()` to use `diskutil unmount` on macOS
- Updated `check_permissions()` - macOS doesn't always require root for diskutil

### 2. **flash_usb.py** - USB Flashing Tool
- Added macOS detection throughout the file
- Updated `check_root()` to be more lenient on macOS
- Implemented macOS USB detection in `list_usb_devices()` using `diskutil list`
- Updated `flash_image()` to:
  - Use `diskutil unmountDisk` before flashing
  - Use `/dev/rdisk` instead of `/dev/disk` for faster writes
  - Use `bs=4m` instead of `bs=4M` (BSD vs GNU dd syntax)
  - Use `diskutil eject` after flashing

## How It Works on macOS

### USB Detection
```bash
# The system uses diskutil to detect external USB drives:
diskutil list -plist external

# Fallback method:
diskutil list
```

### Mounting
```bash
# If not already mounted:
diskutil mount /dev/disk2s1
```

### Unmounting
```bash
# Normal unmount:
diskutil unmount /Volumes/MyUSB

# Force unmount if needed:
diskutil unmount force /Volumes/MyUSB
```

### Flashing (with root)
```bash
# Unmount disk before writing:
diskutil unmountDisk /dev/disk2

# Use raw disk device for faster writes:
dd if=image.img of=/dev/rdisk2 bs=4m

# Eject when done:
diskutil eject /dev/disk2
```

## Usage on macOS

### Basic USB Operations (No Root Required)
```bash
# Run the main application
python3 main.py

# The system will:
# 1. Detect USB drives using diskutil
# 2. List available devices
# 3. Mount/unmount as needed
```

### Flashing USB Drives (Root Required for dd)
```bash
# Flash an image to USB
sudo python3 flash_usb.py

# The system will:
# 1. List external USB drives
# 2. Let you select one
# 3. Unmount all partitions
# 4. Write the image using dd
# 5. Eject the drive when complete
```

## Benefits of Using diskutil

1. **Native macOS Tool** - No additional packages required
2. **Proper Disk Management** - Handles mounting/unmounting cleanly
3. **Fast Raw Disk Access** - Using `/dev/rdisk` for better performance
4. **Safe Ejection** - Ensures all buffers are flushed before removal
5. **Works Without Root** - For detection and basic mounting operations

## Differences from Linux

| Operation | Linux | macOS |
|-----------|-------|-------|
| List USB | `lsblk` | `diskutil list` |
| Mount | `mount` | `diskutil mount` |
| Unmount | `umount` | `diskutil unmount` |
| Format | `mkfs.ext4` | `diskutil eraseDisk` |
| Write Image | `dd bs=4M` | `dd bs=4m` (note lowercase) |
| Device Path | `/dev/sdb` | `/dev/disk2` |
| Fast Write | `/dev/sdb` | `/dev/rdisk2` (raw device) |

## Testing

To test on macOS:

1. **Plug in a USB drive** (⚠️ **WARNING**: Testing may erase data!)

2. **Test USB Detection:**
   ```bash
   python3 main.py
   # Should detect and list your USB drive
   ```

3. **Test Mounting:**
   ```bash
   python3 -c "from src.usb import USBManager; usb = USBManager(); devices = usb.detect_usb_devices(); print(devices)"
   ```

4. **Test Flashing** (use a spare USB!):
   ```bash
   sudo python3 flash_usb.py
   ```

## Troubleshooting

### "diskutil: command not found"
- diskutil is a standard macOS command - you're not on macOS or have a very unusual system

### Permission Denied
- Some operations (like flashing) require sudo
- USB detection and basic mounting usually work without root

### Device Busy
- Make sure the USB isn't being used by another application
- Try force unmount: `diskutil unmount force /Volumes/YourUSB`

### Slow dd Performance
- Make sure you're using `/dev/rdisk` not `/dev/disk`
- The code automatically converts disk to rdisk for better performance

## Example Output

```
🔍 Detecting USB devices...
✓ Found 1 USB device(s)

Available USB Devices:
1. /dev/disk2 - 32.0 GB - SanDisk USB

✓ Selected device: /dev/disk2
✓ Using mounted volume: /Volumes/COLDSTAR
🔄 First instance boot detected on this machine...
✓ Boot instance marker updated
✓ First boot process completed - no restoration needed
```

## Notes

- macOS uses `/Volumes/` for mount points instead of `/mnt/` or `/media/`
- Device names are like `/dev/disk2` not `/dev/sdb`
- Raw devices are `/dev/rdisk2` for faster access
- macOS typically auto-mounts USB drives, so explicit mounting is often unnecessary
- The system handles all these differences automatically!
