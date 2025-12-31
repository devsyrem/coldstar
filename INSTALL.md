# 🚀 Coldstar - Quick Installation Guide

## One-Command Installation

### Windows (PowerShell)

Open PowerShell and run:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Or if you need to allow script execution first:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\install.ps1
```

### macOS

Open Terminal and run:

```bash
chmod +x install.sh && ./install.sh
```

**Note:** On macOS, the installer uses Homebrew to install Python if needed. If you don't have Homebrew, the script will prompt you to install it first.

### Linux

Open Terminal and run:

```bash
chmod +x install.sh && ./install.sh
```

---

## What Gets Installed

The installation script automatically:

1. ✅ **Checks for Python 3.7+** - Installs if missing
2. ✅ **Checks for Rust/Cargo** - Installs if missing  
3. ✅ **Installs Python dependencies** - From requirements files
4. ✅ **Builds Rust components** - Compiles secure_signer
5. ✅ **Verifies everything works** - Runs health checks

---

## Manual Installation (Advanced)

If the automatic installer doesn't work for your system:

### 1. Install Python

**Windows:**
```powershell
winget install Python.Python.3.12
```

**macOS:**
```bash
brew install python3
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install python3 python3-pip
```

### 2. Install Rust

**All platforms:**
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Or visit: https://rustup.rs/

### 3. Install Dependencies

```bash
pip install -r local_requirements.txt
```

### 4. Build Rust Components

```bash
cd secure_signer
cargo build --release
cd ..
```

---

## After Installation

Run the application:

```bash
python main.py
```

Or use the quickstart script:

**Windows:**
```powershell
.\quickstart.ps1
```

**Linux/macOS:**
```bash
./quickstart.sh
```

---

## Troubleshooting

### Python Not Found After Installation

**Windows:** Restart PowerShell or run:
```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
```

**Linux/macOS:** Restart terminal or run:
```bash
source ~/.bashrc  # or ~/.zshrc for macOS
```

### Cargo Not Found After Installation

**All platforms:** Run:
```bash
source $HOME/.cargo/env
```

### Permission Denied (Linux/macOS)

Make sure the script is executable:
```bash
chmod +x install.sh
```

### winget Not Available (Windows)

Install Windows Package Manager from the Microsoft Store, or manually download Python and Rust from:
- Python: https://www.python.org/downloads/
- Rust: https://rustup.rs/

---

## System Requirements

- **OS:** Windows 10+, macOS 10.15+, Linux (any modern distro)
- **Disk Space:** ~2GB (for all dependencies)
- **Internet:** Required for initial download of dependencies

---

## Support

If you encounter issues:

1. Check the error messages - they usually indicate what's missing
2. Try the manual installation steps above
3. Open an issue on GitHub with your OS and error details

---

**Enjoy using Coldstar! 🌟**
