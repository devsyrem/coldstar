# Solana Secure Transaction Signer

A production-ready, security-hardened signing core for Solana transactions, implemented in Rust with seamless Python integration.

## 🎯 Project Overview

This project provides a **secure signing core** that eliminates the risks of handling private keys in Python by:

- **Locking memory in RAM** to prevent swapping to disk
- **Automatic zeroization** of all sensitive data after use
- **Panic-safe cleanup** guarantees (keys are cleared even on errors)
- **Ephemeral key lifecycle** - keys exist only during signing operations
- **Zero plaintext key exposure** - keys never enter Python's memory space

## 🔒 Key Security Features

| Feature | Implementation | Benefit |
|---------|---------------|---------|
| Memory Locking | `mlock()`/`VirtualLock` | Prevents swap to disk |
| Zeroization | Constant-time overwrites | Prevents data remanence |
| Panic Safety | Drop trait guarantees | Cleanup even on crashes |
| Ephemeral Keys | Stack-allocated buffers | Minimal exposure time |
| No Copies | Borrow-based operations | Single key instance |
| Encrypted Storage | AES-256-GCM + Argon2 | Safe key persistence |

## 📁 Project Structure

```
Coldstar SOL/
├── rust_signer/              # Rust signing core
│   ├── src/
│   │   ├── lib.rs           # Library entry point
│   │   ├── main.rs          # CLI binary
│   │   ├── secure_memory.rs # Memory locking & zeroization
│   │   ├── signer.rs        # Core signing logic
│   │   └── ffi.rs           # Python FFI bindings
│   ├── tests/
│   │   └── integration_test.rs
│   ├── Cargo.toml           # Rust dependencies
│   ├── README.md            # Rust library docs
│   └── SECURITY.md          # Security model details
├── python_signer_example.py  # Python integration examples
├── INTEGRATION_GUIDE.md      # Step-by-step integration guide
├── quickstart.sh             # Quick start script (Unix)
├── quickstart.ps1            # Quick start script (Windows)
└── Makefile                  # Build automation
```

## 🚀 Quick Start

### Prerequisites

- **Rust**: 1.70+ ([Install](https://rustup.rs/))
- **Python**: 3.7+ with `ctypes` (standard library)

### Option 1: Automated Setup (Recommended)

**On Unix/Linux/macOS:**
```bash
chmod +x quickstart.sh
./quickstart.sh
```

**On Windows:**
```powershell
.\quickstart.ps1
```

### Option 2: Manual Setup

```bash
# Build the Rust library
cd rust_signer
cargo build --release

# Run tests
cargo test

# Test Python integration
cd ..
python python_signer_example.py
```

## 📖 Usage Examples

### Python FFI Integration (Recommended)

```python
from python_signer_example import SolanaSecureSigner

# Initialize signer
signer = SolanaSecureSigner()

# Create encrypted key container
private_key = bytes.fromhex("your_32_byte_hex_key")
container = signer.create_encrypted_container(
    private_key,
    passphrase="your_strong_passphrase"
)

# Sign a transaction
# SECURITY: Key is decrypted in Rust's locked memory only
signature, signed_tx = signer.sign_transaction(
    container,
    passphrase="your_strong_passphrase",
    transaction=unsigned_transaction_bytes
)

print(f"Signature: {signature.hex()}")
```

### CLI Binary Mode

```bash
# Encrypt a private key
./rust_signer/target/release/solana-signer encrypt \
  --key-file private_key.bin \
  --output encrypted.json

# Sign a transaction
./rust_signer/target/release/solana-signer sign \
  --container encrypted.json \
  --transaction unsigned_tx.bin \
  --output signed_tx.json
```

### Subprocess Integration

```python
import subprocess
import json

# Prepare inputs
container_json = json.dumps(encrypted_container)
tx_hex = transaction_bytes.hex()

# Call CLI via subprocess
result = subprocess.run(
    ["./rust_signer/target/release/solana-signer", "sign-stdin"],
    input=f"{container_json}\n{tx_hex}\n",
    capture_output=True,
    text=True
)

# Parse result
output = json.loads(result.stdout)
signature = bytes.fromhex(output['signature'])
```

## 🔐 Security Model

### Memory Lifecycle Visualization

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: Allocation                                         │
│ • Buffer allocated on heap                                  │
│ • No sensitive data yet                                     │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: Memory Locking                                     │
│ • mlock()/VirtualLock called                                │
│ • Pages locked in RAM (no swap)                             │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: Key Decryption                                     │
│ • Key decrypted directly into locked buffer                 │
│ • Source immediately zeroized                               │
│ • ⚠️ PLAINTEXT KEY IN MEMORY                                │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE 4: Signing                                            │
│ • Signature computed from locked buffer                     │
│ • No key copies made                                        │
│ • ⚠️ PLAINTEXT KEY STILL IN MEMORY                          │
└────────────────────┬────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE 5: Cleanup (Automatic)                                │
│ • Memory zeroized (constant-time)                           │
│ • Pages unlocked                                            │
│ • ✓ No plaintext key remains                                │
│ • Runs even on panic!                                       │
└─────────────────────────────────────────────────────────────┘
```

### Threat Protection Matrix

| Threat | Protected | How |
|--------|-----------|-----|
| Swap file exposure | ✅ | Memory locking |
| Memory dumps | ✅ | Immediate zeroization |
| Crash/panic leaks | ✅ | Panic-safe Drop |
| Timing attacks | ⚠️ | Partial (zeroize is constant-time) |
| Root/admin access | ❌ | OS-level privilege required |
| Cold boot attacks | ❌ | Hardware-level protection needed |

See [rust_signer/SECURITY.md](rust_signer/SECURITY.md) for complete details.

## 🧪 Testing

```bash
# Run all tests
make test

# Or manually:
cd rust_signer && cargo test
python python_signer_example.py
```

## 📚 Documentation

- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - How to integrate with your Python CLI
- **[rust_signer/README.md](rust_signer/README.md)** - Rust library documentation
- **[rust_signer/SECURITY.md](rust_signer/SECURITY.md)** - Security model deep dive
- **[python_signer_example.py](python_signer_example.py)** - Complete Python examples

## 🔧 Build Options

```bash
# Development build
make build

# Release build (optimized)
make release

# Run linter
make lint

# Format code
make format

# Run tests
make test

# Clean build artifacts
make clean
```

## 🎯 Integration with Coldstar SOL

To integrate this secure signer with your existing Coldstar SOL Python CLI:

1. **Build the Rust library**
   ```bash
   cd rust_signer
   cargo build --release
   ```

2. **Convert your key to encrypted format**
   ```python
   from python_signer_example import SolanaSecureSigner
   
   signer = SolanaSecureSigner()
   with open('local_wallet/keypair.json', 'r') as f:
       keypair = json.load(f)
       private_key = bytes(keypair[:32])
   
   container = signer.create_encrypted_container(private_key, "passphrase")
   
   with open('local_wallet/encrypted_keypair.json', 'w') as f:
       json.dump(container, f)
   ```

3. **Update your transaction signing code**
   ```python
   from python_signer_example import SolanaSecureSigner
   
   signer = SolanaSecureSigner()
   signature, signed_tx = signer.sign_transaction(
       encrypted_container,
       passphrase,
       transaction_bytes
   )
   ```

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for complete step-by-step instructions.

## ⚙️ Configuration

### Memory Limits (Unix/Linux)

If you encounter "Failed to lock memory" errors:

```bash
# Temporary
ulimit -l unlimited

# Permanent (add to /etc/security/limits.conf)
* soft memlock unlimited
* hard memlock unlimited
```

### Windows

No special configuration needed. The library uses `VirtualLock` which is always available.

## 🐛 Troubleshooting

### "Secure signer not available"

**Solution:** Build the Rust library:
```bash
cd rust_signer && cargo build --release
```

### "Failed to lock memory"

**Solution:** Increase locked memory limits (see Configuration above)

### "Decryption failed"

**Causes:**
- Wrong passphrase
- Corrupted encrypted container
- Container created with different Argon2 parameters

**Solution:** Recreate the encrypted container from the original key

### Library not found (FFI)

**Solution:** Ensure the library is in the expected location:
- Linux: `rust_signer/target/release/libsolana_secure_signer.so`
- macOS: `rust_signer/target/release/libsolana_secure_signer.dylib`
- Windows: `rust_signer/target/release/solana_secure_signer.dll`

## 🤝 Contributing

Contributions welcome! Please ensure:

1. All tests pass: `cargo test`
2. Code is formatted: `cargo fmt`
3. No clippy warnings: `cargo clippy`
4. Security-critical changes are documented
5. Memory safety guarantees are preserved

## 📄 License

MIT License - See LICENSE file for details

## ⚠️ Security Notice

**This is security-critical software. Before production use:**

1. ✅ Have the code professionally audited
2. ✅ Conduct penetration testing
3. ✅ Verify memory safety with tools (Valgrind, AddressSanitizer)
4. ✅ Test panic scenarios thoroughly
5. ✅ Review the threat model (SECURITY.md)
6. ✅ Ensure compliance with your security requirements

## 🙏 Acknowledgments

Built with:
- [ed25519-dalek](https://github.com/dalek-cryptography/ed25519-dalek) - Ed25519 signatures
- [aes-gcm](https://github.com/RustCrypto/AEADs) - Authenticated encryption
- [argon2](https://github.com/RustCrypto/password-hashes) - Password hashing
- [zeroize](https://github.com/RustCrypto/utils/tree/master/zeroize) - Secure memory clearing
- [region](https://github.com/darfink/region-rs) - Memory locking

## 📞 Support

For issues, questions, or security concerns:
- Open an issue on GitHub
- Review existing documentation
- Check the troubleshooting section above

---

**Made with 🔒 for secure Solana transactions**
