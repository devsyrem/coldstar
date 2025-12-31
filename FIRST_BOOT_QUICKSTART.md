# First Instance Boot Process - Quick Reference

## What It Does

Automatically detects when USB is plugged into a machine and ensures all wallet files are valid and intact.

## When It Runs

✅ **Every time you plug in the USB**  
✅ **Every time you mount the drive**  
✅ **Automatically - no user action needed**

## What It Checks

- `wallet/keypair.json` - Your encrypted private key
- `wallet/pubkey.txt` - Your public address

## What It Does

### If Files Are Valid ✅
- Quick verification check
- Creates/updates backups in `.coldstar/backup/`
- Updates boot marker
- Continues normally

### If Files Are Missing ⚠️
- Detects missing files
- Restores from `.coldstar/backup/`
- Notifies you of restoration
- Continues normally

### If Files Are Corrupted ⚠️
- Detects 0-byte or invalid files
- Restores from backup
- Warns you about corruption
- Continues normally

## User Messages

### First Boot (New Machine)
```
🔄 First instance boot detected on this machine...
✓ Created backup: keypair.json
✓ First boot process completed - no restoration needed
```

### Restoration Needed
```
🔄 First instance boot detected on this machine...
⚠ Missing: keypair.json
✓ Restored keypair.json from backup
✓ First boot process completed - 1 file(s) restored
```

### Subsequent Boots
```
Boot instance verified - checking wallet integrity...
✓ Integrity check completed - no restoration needed
```

## Hidden Files Created

```
.coldstar/
├── last_boot_id      # Tracks which machine/session last used USB
└── backup/           # Automatic backups of wallet files
    ├── keypair.json
    └── pubkey.txt
```

## Key Points

1. **Automatic** - No manual steps required
2. **Safe** - Only restores when actually needed
3. **Smart** - Detects new machines vs same machine
4. **Fast** - Minimal overhead on normal use
5. **Secure** - Backups are encrypted same as originals

## Common Scenarios

| Scenario | What Happens |
|----------|--------------|
| First time plugging in USB | Creates backups, marks boot instance |
| Moving USB to different computer | Detects first boot, verifies files |
| Accidental file deletion | Next mount restores from backup |
| File corruption (power loss) | Detects 0-byte file, restores |
| Normal daily use (same PC) | Quick check, no restoration |

## Testing

Run the test script to see it in action:

```bash
python test_first_boot.py
```

Options:
1. Demonstrate First Boot Process
2. Test Corruption Detection

## Documentation

- Full Details: [FIRST_BOOT_PROCESS.md](FIRST_BOOT_PROCESS.md)
- Implementation: [FIRST_BOOT_IMPLEMENTATION.md](FIRST_BOOT_IMPLEMENTATION.md)
- Main Docs: [README.md](README.md)

## Troubleshooting

**Q: What if both file AND backup are corrupted?**  
A: You'll see an error message. Restore from your offline backup.

**Q: Can I disable this feature?**  
A: Not recommended. It's part of mount process. Delete `.coldstar/` directory to reset.

**Q: Does this slow down mounting?**  
A: Minimal impact - just file existence checks and timestamp comparisons.

**Q: Are backups encrypted?**  
A: Yes, same encryption as the original files (AES-256-GCM).

**Q: What if I don't want backups?**  
A: They're tiny and provide critical data protection. Highly recommended to keep.

---

**B - Love U 3000** ❤️
