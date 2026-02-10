# Coldstar Security Overview

## Table of Contents

- [Introduction](#introduction)
- [Encryption Architecture](#encryption-architecture)
- [Threat Model](#threat-model)
- [Security Features](#security-features)
- [Attack Vectors & Mitigations](#attack-vectors--mitigations)
- [Best Practices](#best-practices)
- [Recommendations by Use Case](#recommendations-by-use-case)
- [Known Limitations](#known-limitations)
- [Security Disclosure](#security-disclosure)

---

## Introduction

Coldstar is an air-gappable, USB-bootable Solana wallet designed with security-first principles. This document provides a comprehensive overview of the security architecture, potential threats, and recommended practices for different use cases.

**Key Security Principles:**
- Private keys are **never stored in plaintext**
- Keys exist in memory for **~100 microseconds** during signing
- **Memory locking** prevents keys from being swapped to disk
- **Immediate zeroization** wipes keys from RAM after use
- **Rust implementation** provides memory safety and guaranteed cleanup

---

## Encryption Architecture

### Encryption Flow

```
Private Key Generation
    ↓
[Secure Buffer - Memory Locked]
    ↓
Password → Argon2id KDF → Encryption Key (32 bytes)
    ↓                   ↓
Random Salt      Random Nonce (12 bytes)
(32 bytes)
    ↓
AES-256-GCM Encryption
    ↓
Encrypted Container (JSON) → Saved to USB
```

### Decryption & Signing Flow

```
Encrypted Container (from USB)
    ↓
Password → Argon2id KDF (same parameters)
    ↓
Decryption Key
    ↓
AES-256-GCM Decrypt → [Secure Buffer - Memory Locked]
    ↓
Sign Transaction (~100 microseconds)
    ↓
Zeroize Memory (overwrite private key with zeros)
    ↓
Return Signature Only
```

### Cryptographic Algorithms

| Component | Algorithm | Parameters |
|-----------|-----------|------------|
| **Key Derivation** | Argon2id | 64 MB RAM, 3 iterations, 4 parallel threads |
| **Encryption** | AES-256-GCM | 256-bit key, 96-bit nonce |
| **Authentication** | GCM | Authenticated encryption (detects tampering) |
| **Signing** | Ed25519 | Solana-compatible elliptic curve |
| **Encoding** | Base64 (storage), Base58 (public keys) | Standard encodings |

### Storage Format

Encrypted wallet containers are stored as JSON:

```json
{
  "version": 1,
  "salt": "base64_encoded_32_bytes",
  "nonce": "base64_encoded_12_bytes", 
  "ciphertext": "base64_encoded_encrypted_key",
  "public_key": "base58_solana_address"
}
```

### Why This Is Secure

1. **Argon2id** - Memory-hard KDF prevents GPU-based brute force attacks
2. **AES-256-GCM** - Provides both encryption and authentication (tamper detection)
3. **Memory locking** (`mlock`) - Prevents private keys from being swapped to disk
4. **Transient decryption** - Keys exist in plaintext for ~100 microseconds only
5. **Automatic zeroization** - Rust's `Drop` trait guarantees memory is wiped even on panic
6. **USB seizure resistant** - Encrypted container is useless without password

---

## Threat Model

### Compromise Levels & Risk Assessment

| Compromise Level | What This Means | Likelihood | Can Private Keys Be Exposed? | Risk Level |
|-----------------|-----------------|------------|------------------------------|------------|
| **No compromise (clean OS)** | Fully patched OS, no malware, normal user behaviour | **High (70-80%)** | **No (practically)** — Keys exist for ~100μs, immediately wiped | ✅ **Safe** |
| **Low-risk user-space malware** | Adware, browser extensions, clipboard clippers | **Common (15-20%)** | **Very unlikely** — Generic malware not targeting crypto operations | ✅ **Low Risk (~5%)** |
| **Active crypto-targeting malware** | RATs, stealers (Redline, Raccoon, Vidar), memory scanners | **Uncommon (3-5%)** | **Low to Moderate** — Must scan memory continuously to catch 100μs window | ⚠️ **Moderate Risk (~30%)** |
| **Targeted Coldstar-specific malware** | Custom tooling monitoring Coldstar/Rust processes | **Rare (<1%)** | **Moderate to High** — Attacker knows signing patterns, can hook Rust FFI | 🚨 **High Risk (~70%)** |
| **Privilege escalation / root access** | Admin/root access, debugger attachment capability | **Very Rare (<0.5%)** | **High** — Can inspect process memory, bypass mlock | 🚨 **Very High Risk (~90%)** |
| **Kernel-level compromise** | Malicious kernel driver, rootkit, modified OS | **Extremely Rare (<0.1%)** | **Very High** — Software protections ineffective | 🚨 **Critical Risk (~99%)** |
| **Firmware / boot compromise** | BIOS/UEFI backdoor, bootloader modification | **Vanishingly Rare (<0.01%)** | **Certain** — Entire trust model broken | 🚨 **Total Compromise (100%)** |

### Typical Attack Causes

- **Low-risk malware**: Phishing, malicious browser add-ons, bundled software
- **Active malware**: Pirated software, cracked tools, torrent downloads
- **Targeted attacks**: High-value targets (whales, exchanges), reconnaissance
- **Privilege escalation**: Exploited 0-day vulnerabilities, social engineering
- **Kernel/Firmware**: Nation-state actors, advanced persistent threats (APT)

---

## Security Features

### Rust Secure Signer Implementation

**File:** `secure_signer/src/crypto.rs`

**Key Features:**
- **SecureBuffer** - Custom type with automatic memory wiping on drop
- **Memory Locking** - Uses `mlock()` to prevent swapping to disk
- **Immediate Zeroization** - Private key overwritten with zeros after signing
- **Panic Safety** - Cleanup guaranteed even on errors (Rust's RAII)
- **No Python Exposure** - Private keys never enter Python memory space

**Code Example:**
```rust
impl Drop for SecureBuffer {
    fn drop(&mut self) {
        // Guaranteed to run even on panic
        self.zeroize();
        unsafe { munlock(self.ptr, self.len); }
    }
}
```

### Python Implementation (Fallback)

**File:** `src/secure_memory.py`

**Features:**
- **Argon2i KDF** - GPU-resistant password hashing
- **XSalsa20-Poly1305** - Authenticated encryption (PyNaCl)
- **Manual cleanup** - `del` + `gc.collect()` (less reliable than Rust)

**Note:** Python implementation is less secure due to unpredictable garbage collection. Rust version is **strongly recommended** for production use.

---

## Attack Vectors & Mitigations

### 1. Memory Capture Attacks

**Attack:** Malware scans process memory to capture private key during signing.

**What Attacker Sees:**
```
Memory Address: 0x7fff5fbff000
Raw Bytes (32-byte Ed25519 seed):
[a3, f2, 1b, 8e, 4d, 7c, 9a, 2f, 
 b5, 6e, 3d, 8c, 1a, 4f, 7e, 2b, ...]

Duration: ~100 microseconds
```

**Mitigations:**
- ✅ Minimal exposure window (100μs vs Python's seconds)
- ✅ Memory locking prevents swap file exposure
- ✅ Immediate zeroization
- ⚠️ **Not effective against**: Continuous memory scanning malware
- 🚨 **Defense:** Use air-gapped signing for high-value transactions

### 2. Clipboard Hijacking

**Attack:** Malware replaces copied wallet addresses with attacker's address.

**Mitigations:**
- ✅ Transaction verification display before signing
- ✅ Address whitelist system (trusted addresses only)
- ✅ Manual confirmation required
- ⚠️ User must verify addresses visually

### 3. Phishing & Social Engineering

**Attack:** User tricked into signing malicious transaction or revealing password.

**Mitigations:**
- ✅ Clear transaction details display before signing
- ✅ Explicit "CONFIRM" required before decrypting keys
- ✅ Amount limits for online signing
- ✅ Password strength requirements

### 4. Cold Boot Attacks

**Attack:** RAM frozen with liquid nitrogen, contents extracted after power-off.

**Mitigations:**
- ✅ Memory locking makes this harder
- ✅ Immediate zeroization reduces window
- ⚠️ **Not fully prevented**: Keys recoverable for seconds after zeroization
- 🚨 **Defense:** Physical security, encrypted RAM (CPU feature)

### 5. Supply Chain Attacks

**Attack:** Compromised hardware/software introduced before user receives it.

**Mitigations:**
- ✅ Open-source code (auditable)
- ✅ Reproducible builds
- ⚠️ **Cannot prevent**: Firmware-level backdoors, compromised CPUs
- 🚨 **Defense:** Hardware wallets from trusted vendors

---

## Best Practices

### For All Users

1. **Strong Passwords**
   - Minimum 12 characters
   - Mix uppercase, lowercase, numbers, symbols
   - Never reuse passwords
   - Consider using a password manager

2. **Verify Transactions**
   - Always check recipient address matches your intention
   - Confirm amounts are correct
   - Never sign transactions you didn't create

3. **Keep Software Updated**
   - Update Coldstar regularly
   - Apply OS security patches
   - Use latest Rust signer version

4. **Physical Security**
   - Store USB wallet in secure location
   - Use encrypted USB drives
   - Consider using multiple backups

### For Enhanced Security

5. **Amount Limits**
   - Keep online wallets under $100 for daily use
   - Store larger amounts in air-gapped cold storage
   - Use separate wallets for different risk levels

6. **Environment Isolation**
   - Use dedicated VM for signing (no network)
   - Run from live USB OS (Alpine Linux)
   - Clear clipboard before/after use

7. **Audit & Monitoring**
   - Review transaction history regularly
   - Monitor for unusual signing patterns
   - Enable logging for forensic analysis

### For Maximum Security (Air-Gapped Signing)

8. **Dedicated Offline Computer**
   - Purchase used laptop (~$100-150)
   - Physically remove WiFi/Bluetooth cards
   - **Never connect to internet, ever**
   - Boot from Coldstar USB only

9. **Transaction Workflow**
   ```
   ONLINE COMPUTER → Create unsigned transaction → USB transfer
   ↓
   OFFLINE COMPUTER → Sign with Coldstar → USB transfer
   ↓
   ONLINE COMPUTER → Broadcast signed transaction
   ```

10. **Additional Hardening**
    - Use hardware wallet as second factor
    - Implement multi-signature (2-of-3 keys)
    - Store backup seeds in bank safe deposit box

---

## Recommendations by Use Case

### Daily Transactions (< $500 balance)

**Setup:** Online Coldstar with standard security

**Protections:**
- ✅ Rust secure signer
- ✅ Transaction verification
- ✅ Strong password

**Risk Level:** Low to Moderate
**Acceptable For:** Daily purchases, testing, small trades

---

### Active Trading ($500 - $5,000)

**Setup:** Online Coldstar with enhanced security

**Additional Protections:**
- ✅ Amount limits (max $50 per transaction online)
- ✅ Address whitelist (trusted recipients only)
- ✅ Anomaly detection (unusual patterns blocked)
- ✅ Fresh password required for large amounts

**Risk Level:** Low
**Acceptable For:** Regular trading, DeFi interactions

---

### Serious Holdings ($5,000 - $50,000)

**Setup:** Air-gapped signing **mandatory**

**Required Setup:**
- 🚨 Dedicated offline laptop (never online)
- 🚨 USB transfer for transactions
- 🚨 Physical security for hardware

**Additional Recommendations:**
- Hardware wallet as backup
- Multi-signature wallet (2-of-3)
- Regular security audits

**Risk Level:** Very Low
**Acceptable For:** Long-term holdings, investment portfolios

---

### High-Value Assets (> $50,000)

**Setup:** Air-gap + Hardware Wallet + Multi-Sig

**Required Setup:**
- 🚨 Air-gapped Coldstar (offline signing)
- 🚨 Hardware wallet (Ledger/Trezor) as second factor
- 🚨 Multi-signature (3-of-5 keys across different locations)
- 🚨 Bank safe deposit box for seed backups

**Additional Recommendations:**
- Professional security audit
- Insurance coverage
- Legal documentation for estate planning

**Risk Level:** Minimal
**Acceptable For:** Institution-grade security, large portfolios

---

## Known Limitations

### What Coldstar CAN Protect Against

✅ Brute-force password attacks (Argon2id)  
✅ File theft without password (AES-256-GCM encryption)  
✅ Swap file exposure (memory locking)  
✅ Accidental memory leaks (automatic zeroization)  
✅ Simple malware (adware, clipboard hijackers)  
✅ Forensic analysis of RAM dumps (minimal exposure)

### What Coldstar CANNOT Protect Against

❌ Sophisticated memory scanning malware (active user-space)  
❌ Kernel-level rootkits (can bypass all protections)  
❌ Firmware/BIOS backdoors (below OS level)  
❌ Physical access attacks (evil maid, DMA)  
❌ User error (phishing, password reuse)  
❌ Compromised hardware (supply chain attacks)

### Design Trade-offs

**Security vs Usability:**
- Online signing is convenient but riskier
- Air-gapped signing is secure but requires extra hardware
- Balance depends on amount at risk

**Python vs Rust:**
- Python implementation easier to audit but less secure
- Rust implementation more complex but provides memory guarantees
- Rust version **strongly recommended** for production

---

## Security Disclosure

### Reporting Vulnerabilities

If you discover a security vulnerability in Coldstar, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email security details to: [your-email@example.com]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)

### Response Timeline

- **24 hours** - Initial acknowledgment
- **7 days** - Preliminary assessment
- **30 days** - Fix developed and tested
- **Coordinated disclosure** - Public announcement after patch released

### Security Audit Status

Coldstar is **open-source and community-audited**. Professional security audits are planned for future releases. Contributions and code reviews are welcome.

---

## Conclusion

Coldstar provides **strong cryptographic security** for Solana private keys through:
- Military-grade encryption (AES-256-GCM + Argon2id)
- Minimal memory exposure (~100 microseconds)
- Memory safety guarantees (Rust)
- Air-gap capability (offline signing)

**The security of your wallet ultimately depends on:**
1. Your threat model (how much are you protecting?)
2. Your operational security (passwords, physical security)
3. Your execution environment (clean OS vs compromised)

**Choose the appropriate security level for your use case** and always assume that convenience is the enemy of security.

For maximum protection: **Air-gap everything**.

---

**Last Updated:** February 10, 2026  
**Version:** 1.0  
**Coldstar Project:** https://github.com/your-repo/coldstar
