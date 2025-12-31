# Solana Secure Signer

A memory-safe Rust library for signing Solana transactions with encrypted private keys. Designed to integrate with Python CLI applications while keeping private keys secure in locked memory.

## Features

- **Memory-Locked Key Storage**: Uses `mlock`/`VirtualLock` to prevent keys from being swapped to disk
- **Automatic Zeroization**: All sensitive data is zeroized on drop (even on panic)
- **Encrypted Key Containers**: Private keys are stored encrypted with Argon2id + AES-256-GCM
- **Ed25519 Signing**: Solana-compatible Ed25519 signatures
- **Python Integration**: FFI and subprocess modes for Python interoperability
- **Panic-Safe**: Cleanup happens even on unexpected errors

## Security Model

The private key lifecycle:

1. **Storage**: Key is encrypted with a strong passphrase (Argon2id for KDF)
2. **Decryption**: Key is decrypted directly into a memory-locked buffer
3. **Signing**: Ed25519 signature is computed within the secure context
4. **Cleanup**: Buffer is zeroized immediately after signing

The plaintext key **never**:
- Leaves the locked memory buffer
- Gets logged or written to disk
- Gets swapped to disk (memory is locked)
- Survives beyond the signing function scope

## Building

```bash
# Debug build
cargo build

# Release build (recommended for production)
cargo build --release

# Run tests
cargo test
```

## Usage

### Command Line

```bash
# Create encrypted container
./target/release/solana-signer create-container \
    --key <base58_private_key> \
    --passphrase "your_secure_passphrase"

# Sign a transaction
./target/release/solana-signer sign \
    --container container.json \
    --passphrase "your_secure_passphrase" \
    --transaction <base64_transaction>

# Check system capabilities
./target/release/solana-signer check
```

### Stdin Mode (Recommended for Automation)

```bash
# Avoid exposing keys in command line
echo '{"action":"sign","container":"...","passphrase":"...","transaction":"..."}' | \
    ./target/release/solana-signer --stdin
```

### Python Integration

```python
from python_integration import SecureSigner

# Initialize signer
signer = SecureSigner(mode="subprocess")

# Create encrypted container
result = signer.create_container(private_key_b58, passphrase)
container_json = json.dumps(result['data'])

# Sign transaction
result = signer.sign_transaction(container_json, passphrase, transaction_bytes)
signature = result['data']['signature']
```

See `python_integration.py` for complete examples.

## API Reference

### Encrypted Key Container

```json
{
  "version": 1,
  "salt": "<base64>",
  "nonce": "<base64>",
  "ciphertext": "<base64>",
  "public_key": "<base58>"
}
```

### Signing Result

```json
{
  "signature": "<base58>",
  "signed_transaction": "<base64>",
  "public_key": "<base58>"
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SIGNER_PASSPHRASE` | Passphrase for encryption/decryption (CLI) |
| `SIGNER_PRIVATE_KEY` | Base58-encoded private key (CLI) |
| `SIGNER_ALLOW_INSECURE_MEMORY` | Set to `1` to allow operation without memory locking |

### Memory Locking Modes

By default, the signer operates in **strict mode** which requires memory locking (`mlock`) to succeed. This prevents private keys from being swapped to disk.

If your system doesn't support `mlock` (e.g., containers without privileges, low ulimit), you can enable **permissive mode**:

```bash
# Enable permissive mode (WARNING: less secure)
export SIGNER_ALLOW_INSECURE_MEMORY=1
./target/release/solana-signer sign ...
```

**Warning**: Permissive mode should only be used for testing or on systems that don't support memory locking. In production, always use strict mode with proper system configuration.

To check if your system supports memory locking:
```bash
./target/release/solana-signer check
```

## Security Considerations

1. **Passphrase Strength**: Use a strong passphrase (20+ characters recommended)
2. **Memory Limits**: Ensure your system allows sufficient `mlock` memory (`ulimit -l`)
3. **Process Isolation**: Subprocess mode provides additional isolation
4. **Container Storage**: Store encrypted containers securely
5. **Strict Mode**: Always use strict mode (default) in production environments

## Dependencies

- `ed25519-dalek`: Ed25519 signing with zeroization support
- `argon2`: Memory-hard key derivation (Argon2id)
- `aes-gcm`: Authenticated encryption
- `zeroize`: Secure memory clearing
- `libc`: Memory locking (Unix)

## License

MIT License - See LICENSE file for details.
