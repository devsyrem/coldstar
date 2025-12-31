# Integration Guide: Adding Secure Signing to Coldstar SOL

This guide shows how to integrate the Rust secure signer into your existing Python Coldstar SOL CLI.

## Overview

The Rust signing core will replace Python-based key handling with secure, memory-locked operations. The integration is designed to be minimally invasive to your existing codebase.

## Integration Strategy

```
Before (Insecure):
┌─────────────────────────────────────────┐
│  Python CLI                              │
│  ├─ Load key from file                  │
│  ├─ Key in Python memory (INSECURE)     │
│  └─ Sign transaction in Python          │
└─────────────────────────────────────────┘

After (Secure):
┌─────────────────────────────────────────┐
│  Python CLI                              │
│  ├─ Load encrypted container            │
│  └─ Call Rust signer ──────────┐        │
└─────────────────────────────────┼────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │  Rust Signing Core      │
                    │  ├─ Decrypt in locked   │
                    │  │   memory              │
                    │  ├─ Sign transaction    │
                    │  └─ Zeroize & return    │
                    └─────────────────────────┘
```


## Security Checklist

After integration, verify:

- [ ] Plaintext keys are deleted (or securely backed up offline)
- [ ] Encrypted containers are created with strong passphrases (12+ characters)
- [ ] Passphrase prompts use `getpass` (not visible on screen)
- [ ] No plaintext keys are logged or printed
- [ ] File permissions on encrypted containers are restrictive (`chmod 600`)
- [ ] Backup encrypted containers securely
- [ ] Test signing with correct and incorrect passphrases

## Rollback Plan

If you need to rollback to the old system:

1. Keep your original `keypair.json` backed up (securely!)
2. Keep the old wallet/transaction code in a separate branch
3. Test thoroughly before deleting plaintext keys

## Performance Considerations

- **FFI mode**: ~0.1ms overhead per signature (negligible)
- **CLI mode**: ~10-50ms overhead per signature (process startup)

For production with high throughput, use FFI mode. For development or occasional use, CLI mode is fine.

## Troubleshooting

### "Secure signer not available"

The Rust library isn't built or not found. Build it:

```bash
cd rust_signer
cargo build --release
```

### "Failed to lock memory"

Your system may have limits on locked memory. Increase the limit:

```bash
# Temporary (current session)
ulimit -l unlimited

# Permanent (add to /etc/security/limits.conf)
* soft memlock unlimited
* hard memlock unlimited
```

### "Decryption failed"

- Check that you're using the correct passphrase
- Verify the encrypted container file isn't corrupted
- Try recreating the container from the original key

## Next Steps

1. **Integrate with UI**: Add passphrase prompts to your UI
2. **Key Rotation**: Implement periodic key rotation
3. **Multi-Sig**: Extend for multi-signature support
4. **Hardware Integration**: Consider HSM integration for production

## Support

For issues or questions:
- Check the README.md and SECURITY.md
- Review the example code in python_signer_example.py
- Open an issue with detailed logs and steps to reproduce
