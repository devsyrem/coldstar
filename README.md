<div align="center">

# ❄️ Coldstar

### CLI-First Cold Wallet System with RAM-Only Key Exposure

[![License](https://img.shields.io/badge/license-Open%20Source-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/rust-stable-orange.svg)](https://www.rust-lang.org/)
[![Status](https://img.shields.io/badge/status-Proof%20of%20Concept-yellow.svg)](#)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[Quick Start](#-quick-start) • [Documentation](documentation/) • [Security](SECURITY.md) • [Architecture](documentation/ARCHITECTURE.md) • [Whitepaper](documentation/whitepaper.md)

</div>

---

## ⚠️ Important Notice

> **Proof of Concept — Experimental Software**
>
> Coldstar is a **proof of concept** and an **experimental version**. It is **not production-ready** and should **not** be used to secure real assets. This repository exists for **developers and researchers** in the Coldstar community to understand, evaluate, and improve the Coldstar process. 
>
> 🤝 Contributions, feedback, and security reviews are **welcome and encouraged**.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features-at-a-glance)
- [Quick Start](#-quick-start)
- [Core Concept](#-core-concept)
- [How It Works](#-how-it-works)
- [Encryption Flow](#-encryption--decryption-flow)
- [Supported Use Cases](#-supported-use-cases)
- [Documentation](#-documentation)
- [Development](#-development-and-testing)
- [License](#-license)

---

## 🌟 Overview

Coldstar is a **CLI-first cold wallet system** that transforms any standard USB drive into a disposable, RAM-only signing medium. It eliminates long-lived private key exposure by ensuring keys are decrypted only in volatile memory and only for the duration of transaction signing.

**Key Innovation:** No permanent trusted hardware. No secure elements. No vendor lock-in.

This repository contains the core implementation, documentation, and tooling required to initialize USB-based cold wallets and perform offline transaction signing.

---

## ✨ Features at a Glance

<table>
<tr>
<td width="33%" valign="top">

### 🔐 Security
- **RAM-only** private key exposure
- **Microsecond** key lifetime
- **No proprietary** hardware
- **Memory-locked** buffers (mlock)
- **Automatic** key zeroization

</td>
<td width="33%" valign="top">

### 🛠️ Design
- **CLI-first** and automation-native
- **Fully scriptable** and headless
- **Open-source** and auditable
- **Asset-agnostic** by design
- **Disposable** USB storage

</td>
<td width="33%" valign="top">

### ⚡ Workflow
- **No GUI** dependency
- **Deterministic** builds
- **CI/CD** compatible
- **Air-gap** friendly
- **Cross-platform** support

</td>
</tr>
</table>

---

## 🚀 Quick Start

### 📦 Prerequisites

Coldstar requires both **Python 3.8+** and **Rust** to be installed on your system.

<details>
<summary><b>🐍 Installing Python</b></summary>

#### Windows (PowerShell)
```powershell
# Download and install Python from official website
winget install Python.Python.3.11

# Or download from: https://www.python.org/downloads/
# Make sure to check "Add Python to PATH" during installation
```

#### macOS
```bash
# Using Homebrew
brew install python@3.11

# Or download from: https://www.python.org/downloads/
```

#### Linux
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip

# Fedora
sudo dnf install python3 python3-pip

# Arch
sudo pacman -S python python-pip
```

**Verify installation:**
```bash
python --version
# or
python3 --version
```

</details>

<details>
<summary><b>🦀 Installing Rust</b></summary>

#### All Platforms (Recommended)
```bash
# Install rustup (Rust installer)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Follow the on-screen instructions
# After installation, restart your terminal
```

#### Windows (Alternative using winget)
```powershell
winget install Rustlang.Rustup
```

**Verify installation:**
```bash
cargo --version
rustc --version
```

</details>

---

### ⚡ Installation & Running

### ⚡ Installation & Running

**1️⃣ Clone the repository:**
```bash
git clone https://github.com/devsyrem/coldstar.git
cd coldstar
```

**2️⃣ Run the application:**
```bash
python main.py
```

The application will automatically:
- ✅ Build the Rust secure signer on first run
- ✅ Set up the necessary environment
- ✅ Launch the interactive CLI

> 💡 **Note:** The first run will take a few minutes as it compiles the Rust components. Subsequent runs will be much faster.

---

## 💡 Core Concept

Traditional hardware wallets rely on permanent devices that store private keys for their entire lifetime. This creates **persistent trust anchors**, **supply-chain risk**, and **physical attack surfaces**.

**Coldstar challenges this model** by removing permanent trusted hardware entirely.

### 🔄 Instead of trusting devices, Coldstar trusts:

| Traditional Approach | Coldstar Approach |
|---------------------|-------------------|
| 🔒 Proprietary hardware | ✅ Open-source, auditable software |
| 🏭 Vendor-controlled firmware | ✅ User-controlled operating systems |
| 📅 Long-lived key exposure | ✅ Extremely short-lived key exposure in RAM |

### 🔐 Private keys are:

- ✅ **Encrypted at rest** on user-supplied USB storage
- ✅ **Decrypted only** in system memory
- ✅ **Explicitly wiped** after signing completes

> 🎯 **Key Insight:** The USB drive is **not** a signing device. It is **encrypted storage only**.

---

## 🏗️ How It Works

```mermaid
graph LR
    A[🔧 Initialize USB] --> B[🔑 Generate Keys]
    B --> C[🔐 Encrypt to USB]
    C --> D[📝 Sign Transaction]
    D --> E[💾 Load to RAM]
    E --> F[🔓 Decrypt in Memory]
    F --> G[✍️ Sign]
    G --> H[🗑️ Wipe Memory]
```

### Step-by-Step Process

1. **🔧 Initialize USB Drive**  
   A standard USB drive is initialized using the Coldstar CLI

2. **🔑 Generate Key Pairs**  
   Cryptographic key pairs are generated and encrypted directly onto the USB

3. **📝 When signing is required:**
   - Encrypted key material is loaded into memory
   - Decryption occurs **only in RAM**
   - The transaction is signed

4. **🗑️ Immediate Cleanup**  
   Decrypted key material is immediately erased from memory

5. **✅ Security Achieved**  
   No plaintext keys persist on disk or hardware

> 🔒 **At no point does any powered device permanently store a usable private key.**

📖 **See [ARCHITECTURE.md](documentation/ARCHITECTURE.md) for detailed technical architecture and system design.**

---

## 🔐 Encryption & Decryption Flow

### 🔍 Physical Hardware Path and Data Protection

Coldstar's security model depends on understanding exactly where sensitive data exists in physical hardware and how it's protected at each stage.

<details>
<summary><b>📤 1. Key Generation and Encryption (Initial Setup)</b></summary>

```
┌─────────────────────────────────────────────────────────────────┐
│ HARDWARE: CPU + System RAM (Volatile)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: Random Seed Generation                                │
│  ┌──────────────────────────────────────────┐                  │
│  │ CPU's Hardware RNG (/dev/urandom)        │                  │
│  │ → 32 bytes Ed25519 seed                  │                  │
│  │ → Generated in CPU registers             │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓ (copied to RAM)                                  │
│  ┌──────────────────────────────────────────┐                  │
│  │ Rust Secure Buffer (mlock'd RAM)         │                  │
│  │ • Memory page locked (cannot swap)       │                  │
│  │ • 32-byte plaintext private key          │ ← PLAINTEXT HERE │
│  │ • Protected by OS memory isolation       │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓                                                  │
│  Step 2: User Passphrase Entry                                 │
│  ┌──────────────────────────────────────────┐                  │
│  │ Keyboard → Terminal → RAM buffer         │                  │
│  │ Passphrase: "user_secret_password"       │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓                                                  │
│  Step 3: Key Derivation (Argon2id)                             │
│  ┌──────────────────────────────────────────┐                  │
│  │ CPU executes Argon2id:                   │                  │
│  │ • 64 MB memory-hard operation            │                  │
│  │ • 3 iterations                           │                  │
│  │ • 32-byte random salt                    │                  │
│  │ → Produces 32-byte AES-256 key           │                  │
│  │ → Stored in mlock'd RAM                  │ ← PLAINTEXT HERE │
│  └──────────────────────────────────────────┘                  │
│              ↓                                                  │
│  Step 4: AES-256-GCM Encryption                                │
│  ┌──────────────────────────────────────────┐                  │
│  │ CPU encrypts:                            │                  │
│  │ • Input: 32-byte plaintext key           │                  │
│  │ • Key: Derived AES key                   │                  │
│  │ • Nonce: 12-byte random                  │                  │
│  │ • Output: 48-byte ciphertext + auth tag  │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓                                                  │
│  Step 5: Immediate Zeroization                                 │
│  ┌──────────────────────────────────────────┐                  │
│  │ Plaintext key OVERWRITTEN in RAM:        │                  │
│  │ 0x42...A7 → 0x00000000000000000000       │                  │
│  │ Derived AES key → 0x000000000000         │                  │
│  │ Passphrase buffer → 0x000000000000       │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓ (only encrypted data remains)                    │
└─────────────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────────────┐
│ HARDWARE: USB Flash Storage (Non-Volatile)                      │
├─────────────────────────────────────────────────────────────────┤
│  JSON File Written to NAND Flash:                              │
│  {                                                              │
│    "version": 1,                                               │
│    "salt": "base64_encoded_32_bytes",                          │
│    "nonce": "base64_encoded_12_bytes",                         │
│    "ciphertext": "base64_encoded_48_bytes",  ← ENCRYPTED ONLY  │
│    "public_key": "base58_encoded_pubkey"                       │
│  }                                                              │
│                                                                 │
│  ⚠️  Private key NEVER stored in plaintext on USB              │
│  ✓  USB can be read without exposing private key               │
│  ✓  USB can be physically seized without key compromise        │
└─────────────────────────────────────────────────────────────────┘
```

</details>

<details>
<summary><b>📥 2. Transaction Signing (Decryption and Use)</b></summary>

```
┌─────────────────────────────────────────────────────────────────┐
│ HARDWARE: USB Flash Storage (Non-Volatile)                      │
├─────────────────────────────────────────────────────────────────┤
│  Step 1: Read Encrypted Container from USB                     │
│  ┌──────────────────────────────────────────┐                  │
│  │ USB NAND Flash → USB Controller →        │                  │
│  │ USB Bus → OS Kernel → Python Process     │                  │
│  │                                           │                  │
│  │ Encrypted data (48 bytes ciphertext)     │ ← ENCRYPTED ONLY │
│  │ + Salt (32 bytes)                        │                  │
│  │ + Nonce (12 bytes)                       │                  │
│  └──────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
              ↓ (encrypted data copied to RAM)
┌─────────────────────────────────────────────────────────────────┐
│ HARDWARE: System RAM - Python Memory Space                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────┐                  │
│  │ Python dict object in heap:              │                  │
│  │ {                                        │                  │
│  │   "ciphertext": [bytes],  ← ENCRYPTED    │                  │
│  │   "salt": [bytes],                       │                  │
│  │   "nonce": [bytes]                       │                  │
│  │ }                                        │                  │
│  │                                          │                  │
│  │ ⚠️ NO PLAINTEXT KEY IN PYTHON MEMORY     │                  │
│  └──────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
              ↓ (FFI call: Python → Rust)
┌─────────────────────────────────────────────────────────────────┐
│ HARDWARE: System RAM - Rust Memory Space (Isolated)             │
├─────────────────────────────────────────────────────────────────┤
│  Step 2: Passphrase Entry                                      │
│  ┌──────────────────────────────────────────┐                  │
│  │ User types passphrase                    │                  │
│  │ → Passed to Rust via FFI                 │                  │
│  │ → Copied into Rust String                │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓                                                  │
│  Step 3: Key Re-Derivation (Argon2id)                          │
│  ┌──────────────────────────────────────────┐                  │
│  │ Rust Secure Buffer (mlock'd):            │                  │
│  │                                           │                  │
│  │ Argon2id(passphrase, salt) →             │                  │
│  │   32-byte AES-256 key                    │ ← PLAINTEXT HERE │
│  │                                           │                  │
│  │ • mlock() called - RAM locked            │                  │
│  │ • Cannot be swapped to disk              │                  │
│  │ • Python CANNOT access this memory       │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓                                                  │
│  Step 4: AES-256-GCM Decryption                                │
│  ┌──────────────────────────────────────────┐                  │
│  │ CPU decrypts in Rust mlock'd buffer:     │                  │
│  │                                           │                  │
│  │ Ciphertext (48 bytes) →                  │                  │
│  │   AES-GCM-Decrypt(key, nonce) →          │                  │
│  │     32-byte Ed25519 seed                 │ ← PLAINTEXT HERE │
│  │                                           │                  │
│  │ • Plaintext key ONLY in locked RAM       │                  │
│  │ • NEVER copied to Python                 │                  │
│  │ • NEVER written to disk                  │                  │
│  │ • NEVER in swap file                     │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓                                                  │
│  Step 5: Ed25519 Signature Generation                          │
│  ┌──────────────────────────────────────────┐                  │
│  │ CPU executes Ed25519 signing:            │                  │
│  │                                           │                  │
│  │ Private Key (32 bytes) +                 │ ← PLAINTEXT HERE │
│  │ Transaction Message (N bytes) →          │                  │
│  │   CPU Ed25519 ops →                      │                  │
│  │     64-byte signature                    │                  │
│  │                                           │                  │
│  │ • Signing in CPU registers + L1 cache    │                  │
│  │ • Private key in mlock'd RAM             │                  │
│  │ • Duration: ~100 microseconds            │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓                                                  │
│  Step 6: Immediate Zeroization                                 │
│  ┌──────────────────────────────────────────┐                  │
│  │ Rust Drop trait executes:                │                  │
│  │                                           │                  │
│  │ Private key buffer → 0x00000000000000    │                  │
│  │ Derived AES key → 0x00000000000000       │                  │
│  │ Passphrase → 0x00000000000000            │                  │
│  │                                           │                  │
│  │ • Guaranteed even on panic               │                  │
│  │ • munlock() called - RAM unlocked        │                  │
│  │ • Memory returned to OS                  │                  │
│  └──────────────────────────────────────────┘                  │
│              ↓ (only signature returned)                        │
└─────────────────────────────────────────────────────────────────┘
              ↓ (FFI return: Rust → Python)
┌─────────────────────────────────────────────────────────────────┐
│ HARDWARE: System RAM - Python Memory Space                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────┐                  │
│  │ Python receives:                         │                  │
│  │ • 64-byte signature (PUBLIC)             │ ✓ SAFE           │
│  │ • Transaction with signature attached    │ ✓ SAFE           │
│  │                                          │                  │
│  │ ⚠️ Private key NEVER entered Python      │                  │
│  └──────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

</details>

---

### 🛡️ Memory Protection Mechanisms

<details>
<summary><b>🔒 mlock() - Preventing Swap to Disk</b></summary>

```
Normal RAM page:                   mlock'd RAM page:
┌──────────────┐                  ┌──────────────┐
│ RAM (active) │                  │ RAM (locked) │
└──────┬───────┘                  └──────────────┘
       │ OS may swap                     ↑
       ↓                                  │
┌──────────────┐                   Cannot be moved
│ Swap file on │                   to disk by OS
│ disk/SSD     │
└──────────────┘

Private keys ONLY in mlock'd pages → Never touch persistent storage
```

</details>

<details>
<summary><b>🗑️ Memory Zeroization</b></summary>

```
Before Zeroization:         After Zeroization:
RAM Address: 0x7F3A8000     RAM Address: 0x7F3A8000
┌──────────────────────┐    ┌──────────────────────┐
│ 0x42 (private key)   │    │ 0x00 (zeroed)        │
│ 0x8F                 │    │ 0x00                 │
│ 0xA7                 │    │ 0x00                 │
│ ...  (32 bytes)      │    │ ...  (32 bytes)      │
└──────────────────────┘    └──────────────────────┘

• Overwrites with zeros before deallocation
• Prevents recovery from heap analysis
• Protects against cold boot attacks (partially)
```

</details>

<details>
<summary><b>🔐 Process Memory Isolation</b></summary>

```
┌────────────────────────────────────────────────────┐
│ Operating System (Kernel Space)                    │
├────────────────────────────────────────────────────┤
│                                                    │
│  ┌─────────────────┐      ┌──────────────────┐    │
│  │ Python Process  │      │ Other Processes  │    │
│  │ PID: 1234       │      │ PID: 5678, ...   │    │
│  ├─────────────────┤      └──────────────────┘    │
│  │ Python heap     │             ↑                 │
│  │ (encrypted data)│             │                 │
│  └────────┬────────┘             │                 │
│           │ FFI call             │                 │
│           ↓                      │                 │
│  ┌─────────────────┐             │                 │
│  │ Rust library    │             │                 │
│  │ (same process)  │             │                 │
│  ├─────────────────┤             │                 │
│  │ mlock'd buffer  │      ← OS blocks access       │
│  │ (plaintext key) │             │                 │
│  └─────────────────┘             │                 │
│                                  │                 │
│  • Rust memory isolated from Python by design     │
│  • mlock'd pages protected by OS kernel            │
│  • Other processes cannot access this memory       │
└────────────────────────────────────────────────────┘
```

</details>

---

---

### 📊 Data States Across Hardware

| Location | Data State | Duration | Hardware |
|----------|-----------|----------|----------|
| 💾 **USB NAND Flash** | 🔒 Encrypted | Permanent (until deleted) | Non-volatile flash memory |
| 🔌 **USB → Computer** | 🔒 Encrypted | Microseconds (transfer) | USB bus, PCIe controller |
| 🐍 **Python RAM** | 🔒 Encrypted | Seconds (during signing) | DRAM (swappable) |
| 🦀 **Rust mlock'd RAM** | ⚠️ **PLAINTEXT** | **~100 microseconds** | **DRAM (locked, non-swappable)** |
| ⚡ **CPU Registers/Cache** | ⚠️ **PLAINTEXT** | **~10 nanoseconds** | **L1/L2 cache, registers** |
| 🌐 **Network transmission** | ✅ Signature only | N/A | Never contains private key |

---

### ✅ Security Guarantees

<table>
<tr>
<td width="50%" valign="top">

#### ✅ What is Protected

- ✅ Private key never stored in plaintext on persistent storage
- ✅ Private key never exists in Python-accessible memory
- ✅ Private key automatically erased after signing (even on crash/panic)
- ✅ Private key cannot be swapped to disk during signing
- ✅ Encrypted container can be safely copied, backed up, or transmitted

</td>
<td width="50%" valign="top">

#### ⚠️ What is NOT Protected Against

- ⚠️ Memory dumps while private key is in RAM (requires root + precise timing)
- ⚠️ Compromised OS with kernel-level access
- ⚠️ Hardware keyloggers capturing passphrase
- ⚠️ Cold boot attacks (if RAM extracted within seconds)
- ⚠️ Physical tampering with CPU/RAM hardware

</td>
</tr>
</table>

> 📖 **See [SECURE_SIGNER_README.md](documentation/SECURE_SIGNER_README.md) for detailed information on the Rust-based secure signer implementation.**

---

### ⚖️ Key Differences from Hardware Wallets

### ⚖️ Key Differences from Hardware Wallets

| Aspect | 🏪 Hardware Wallet | ❄️ Coldstar |
|--------|-------------------|-------------|
| **Persistent key storage** | ✅ Yes (secure element) | ❌ No (RAM only during signing) |
| **Physical attack surface** | 🔒 Permanent device | 💿 Disposable USB + computer RAM |
| **Decryption location** | 🔐 Inside secure chip | 💾 System RAM (mlock'd) |
| **Key lifetime** | 📅 Years | ⚡ Microseconds |
| **Supply chain risk** | ⚠️ High (proprietary hardware) | ✅ Low (commodity USB + open source) |
| **OS compromise impact** | 🛡️ Protected by hardware | ⚠️ Vulnerable |

---

## 🎯 Supported Use Cases

Coldstar is **asset-agnostic** and designed to support modern on-chain workflows, including:

<table>
<tr>
<td width="50%" valign="top">

### 💰 Asset Types
- ⚡ Native Solana transactions
- 🪙 SPL tokens
- 💵 Stablecoins
- 🥇 Tokenized commodities (e.g. PAXG)

</td>
<td width="50%" valign="top">

### 🔧 Operations
- 📈 Tokenized equities (xStocks)
- 🛠️ Custom program instructions
- 🏦 Solana staking and delegation
- 🔄 All cold-signing security models

</td>
</tr>
</table>

> 🎯 All assets are handled under the same cold-signing security model.

---

## 🤔 Why Coldstar Exists

Hardware wallets improved security, but introduced **new problems**:

<table>
<tr>
<td width="50%" valign="top">

### ❌ Hardware Wallet Issues
- 🔒 Permanent key storage
- 🏭 Vendor trust assumptions
- ⚠️ Firmware and supply-chain risk
- 🐌 Poor automation support
- 🖱️ Manual, GUI-driven workflows

</td>
<td width="50%" valign="top">

### ✅ Coldstar Solutions
- ⚡ Temporary, RAM-only keys
- 🔓 No vendor trust required
- 📖 Open-source and auditable
- 🤖 Automation-native design
- ⌨️ CLI-first workflows

</td>
</tr>
</table>

**Coldstar removes the concept of a permanent trusted device entirely.**

Any USB drive can be:
- 🔄 **Rotated** — Replace with a new one anytime
- 💥 **Destroyed** — No regrets about hardware cost
- 🔁 **Replaced** — Use any commodity USB
- 🗑️ **Treated as disposable** — No attachment to specific devices

> 💡 There are no serial numbers, proprietary chips, or vendor lock-in.

📖 **See [whitepaper.md](documentation/whitepaper.md) for the complete technical whitepaper and theoretical foundations.**

---

## 🛡️ Threat Model and Assumptions

Coldstar is **explicit** about its security boundaries.

<table>
<tr>
<td width="50%" valign="top">

### ✅ Protects Against
- ⏰ Long-lived key exposure
- 🔓 Firmware backdoors
- 🏭 Hardware supply-chain manipulation
- 🔒 Persistent device compromise
- 👮 Seizure or fingerprinting of signing hardware

</td>
<td width="50%" valign="top">

### 📋 Assumes
- 🖥️ User controls their operating system
- ✅ Runtime environment is not fully compromised
- 👨‍💻 Users are capable of auditing CLI-based tooling

</td>
</tr>
</table>

> 💡 **Coldstar does not attempt to hide these assumptions behind hardware abstractions.**

---

## 🔄 First Instance Boot Process

> **✨ New Feature:** Automatic file integrity and restoration system.

Every time you plug your USB cold wallet into a machine, Coldstar automatically:

- ✅ Detects if this is the first time on this machine/session
- ✅ Verifies all critical wallet files (`keypair.json`, `pubkey.txt`)
- ✅ Restores missing or corrupted files from backup (if needed)
- ✅ Creates/updates backups of valid files
- ✅ Updates boot instance markers

> 💡 **This is not a restoration function** — it's an intelligent boot detection mechanism that ensures wallet integrity across different machines and reboots.

### 🔧 How It Works

1. **🆔 Boot Detection:** Generates unique boot instance ID from machine hostname + process + timestamp
2. **🔍 File Verification:** Checks critical files for existence and corruption (0-byte detection)
3. **🔄 Smart Restoration:** Only restores files if actually missing or corrupted
4. **💾 Automatic Backups:** Creates backups in `.coldstar/backup/` directory on USB

### 📁 Storage Structure

```
USB Drive
├── wallet/
│   ├── keypair.json          # 🔐 Encrypted private key
│   └── pubkey.txt             # 🔑 Public address
├── inbox/                     # 📥 Unsigned transactions
├── outbox/                    # 📤 Signed transactions  
└── .coldstar/                 # 🔒 Hidden system directory
    ├── last_boot_id           # 🆔 Boot instance tracker
    └── backup/                # 💾 Automatic backups
        ├── keypair.json
        └── pubkey.txt
```

### 🎯 Benefits

- ⚡ **Zero User Intervention** — Everything happens automatically
- 🖥️ **Cross-Machine Compatibility** — USB works seamlessly on any machine
- 🔍 **Corruption Detection** — Catches file system errors immediately
- 🛡️ **Protection Against Accidents** — Files can be recovered from backup
- 🚀 **Performance Optimized** — Only runs when needed

### 📖 Documentation

- [FIRST_BOOT_PROCESS.md](documentation/FIRST_BOOT_PROCESS.md) - Detailed technical specification
- [FIRST_BOOT_IMPLEMENTATION.md](documentation/FIRST_BOOT_IMPLEMENTATION.md) - Implementation details
- [FIRST_BOOT_QUICKSTART.md](documentation/FIRST_BOOT_QUICKSTART.md) - Quick start guide
- [STEP7_VISUAL_GUIDE.md](STEP7_VISUAL_GUIDE.md) - Visual guide to the 7-step USB flash process
- [STEP7_QUICK_REFERENCE.md](STEP7_QUICK_REFERENCE.md) - Quick reference for Step 7

---

## 🆚 Comparison

### Coldstar vs. Traditional Hardware Wallets

<table>
<tr>
<td width="50%" valign="top">

### ❄️ Coldstar Advantages
- ❌ No permanent signing device
- ❌ No secure element
- ❌ No firmware approval process
- ❌ No vendor trust anchor
- ✅ Full automation support
- ✅ Deterministic and scriptable workflows

</td>
<td width="50%" valign="top">

### 🏪 Hardware Wallet Characteristics
- ✅ Dedicated signing device
- ✅ Secure element chip
- ⚠️ Firmware updates required
- ⚠️ Trust in vendor
- ❌ Limited automation
- ❌ Manual GUI workflows

</td>
</tr>
</table>

> 💡 Compared to open-source hardware wallets, **Coldstar removes the final dependency: the device itself.**

---

## 💻 CLI-First by Design

Coldstar is built for **power users and automation**:

<table>
<tr>
<td width="50%" valign="top">

### 🎯 Target Environments
- 🖥️ Headless environments
- 🔄 CI/CD pipelines
- 🤖 Automated trading systems
- ✈️ Air-gapped workflows
- 📜 Deterministic scripting

</td>
<td width="50%" valign="top">

### 🚫 What It's NOT
- ❌ Not a consumer wallet
- ❌ No GUI dependency
- ❌ No browser extension
- ❌ No background daemon
- ❌ Not beginner-focused

</td>
</tr>
</table>

> 💡 **This is not a consumer wallet and does not aim to be one.**

---

## 👥 Intended Audience

Coldstar is built for **technical users** who value control and transparency:

- 👨‍💻 **Developers** signing complex transactions
- 📊 **Traders** managing significant on-chain value
- 🔧 **Operators** who require explicit control
- 🔐 **Security-conscious users** who understand their environment

> ⚠️ **Not intended for beginners or retail-first UX.**

---

## 🔍 Open Source and Verifiability

Coldstar is designed to be:

- 👁️ **Fully inspectable** — All code is open-source
- 🏗️ **Deterministically buildable** — Reproducible builds
- 🔬 **Auditable by design** — Security by verification, not trust

> 💡 **Security claims are meant to be verifiable, not trusted.**

### 📖 Integration Documentation

- [INTEGRATION_GUIDE.md](documentation/INTEGRATION_GUIDE.md) - Guide for integrating Coldstar
- [INTEGRATION_STATUS.md](documentation/INTEGRATION_STATUS.md) - Current integration status
- [RUST_INTEGRATION_COMPLETE.md](documentation/RUST_INTEGRATION_COMPLETE.md) - Rust signer details

### 📊 Project Status

- [PROJECT_COMPLETE.md](documentation/PROJECT_COMPLETE.md) - Project completion status
- [DELIVERABLES.md](documentation/DELIVERABLES.md) - Project deliverables and roadmap

---

## 📂 Repository Structure

```
coldstar/
├── 📁 src/                    # Source code
│   ├── cli/                   # Command-line interface
│   ├── crypto/                # Key generation, encryption, memory handling
│   └── signing/               # Transaction signing logic
├── 📁 secure_signer/          # Rust-based secure signer
├── 📁 documentation/          # Architecture, threat model, design notes
├── 📁 attached_assets/        # Additional resources
├── 🐍 main.py                 # Main entry point
├── 🔧 config.py               # Configuration
├── 📄 README.md               # This file
└── 📋 SECURITY.md             # Security policy
```

---

## 🧪 Development and Testing

### 🧪 Test Files
- [test_first_boot.py](test_first_boot.py) - First boot functionality tests
- [test_transaction.py](test_transaction.py) - Transaction signing tests

### 🚀 Legacy Setup Scripts

> ⚠️ **Note:** Requires Rust/Python pre-installed

- **Windows:** [quickstart.ps1](quickstart.ps1) - PowerShell setup script
- **Linux/Mac:** [quickstart.sh](quickstart.sh) - Bash setup script

---

## ⚠️ Disclaimer

> **Important:** Users are responsible for understanding the risks, verifying the code, and operating within the documented security assumptions.

---

## 📜 License

Open-source. See the [LICENSE](LICENSE) file for details.

---

<div align="center">

## 📚 Documentation

**Explore the full documentation for in-depth technical details:**

| Category | Documentation |
|----------|--------------|
| 🏗️ **Architecture** | [ARCHITECTURE.md](documentation/ARCHITECTURE.md) |
| 📖 **Whitepaper** | [whitepaper.md](documentation/whitepaper.md) |
| 🔐 **Security** | [SECURITY.md](SECURITY.md) |
| 🦀 **Secure Signer** | [SECURE_SIGNER_README.md](documentation/SECURE_SIGNER_README.md) |
| 🔄 **First Boot** | [FIRST_BOOT_PROCESS.md](documentation/FIRST_BOOT_PROCESS.md) |
| 🔧 **Integration** | [INTEGRATION_GUIDE.md](documentation/INTEGRATION_GUIDE.md) |

---

### 🤝 Contributing

We welcome contributions! Please see our contributing guidelines and submit pull requests.

### 💬 Community

Questions? Issues? Feedback? Feel free to open an issue on GitHub.

---

Made with ❄️ by the Coldstar community

**[⬆ Back to Top](#-coldstar)**

</div>
