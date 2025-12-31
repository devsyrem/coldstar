#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  COLDSTAR AUTO-INSTALLER (Linux/macOS/Unix)
#  One-command installation for all dependencies
# ═══════════════════════════════════════════════════════════════════

set -e  # Exit on error

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              COLDSTAR - AUTO INSTALLER                         ║"
echo "║         Installing all dependencies automatically...           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Check/Install Python
# ═══════════════════════════════════════════════════════════════════

echo "━━━━ Step 1: Checking Python... ━━━━"

if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ Python already installed: $PYTHON_VERSION"
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version)
    if [[ $PYTHON_VERSION == *"Python 3"* ]]; then
        echo "✓ Python already installed: $PYTHON_VERSION"
        PYTHON_CMD="python"
    else
        echo "⚠ Python 2 found, need Python 3..."
        PYTHON_CMD=""
    fi
else
    PYTHON_CMD=""
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "⚠ Python 3 not found. Installing Python..."
    
    # Detect OS and install accordingly
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt-get &> /dev/null; then
            # Debian/Ubuntu
            echo "  Using apt-get to install Python..."
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-pip python3-venv
            PYTHON_CMD="python3"
        elif command -v yum &> /dev/null; then
            # RedHat/CentOS/Fedora
            echo "  Using yum to install Python..."
            sudo yum install -y python3 python3-pip
            PYTHON_CMD="python3"
        elif command -v dnf &> /dev/null; then
            # Fedora (newer)
            echo "  Using dnf to install Python..."
            sudo dnf install -y python3 python3-pip
            PYTHON_CMD="python3"
        elif command -v pacman &> /dev/null; then
            # Arch Linux
            echo "  Using pacman to install Python..."
            sudo pacman -S --noconfirm python python-pip
            PYTHON_CMD="python3"
        else
            echo "❌ Unsupported Linux distribution. Please install Python 3.7+ manually."
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            echo "  Using Homebrew to install Python..."
            brew install python3
            PYTHON_CMD="python3"
        else
            echo "❌ Homebrew not found. Please install Homebrew first:"
            echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            exit 1
        fi
    else
        echo "❌ Unsupported OS. Please install Python 3.7+ manually."
        exit 1
    fi
    
    echo "✓ Python installed successfully!"
fi

echo ""

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Check/Install Rust
# ═══════════════════════════════════════════════════════════════════

echo "━━━━ Step 2: Checking Rust/Cargo... ━━━━"

if command -v cargo &> /dev/null; then
    CARGO_VERSION=$(cargo --version)
    echo "✓ Rust/Cargo already installed: $CARGO_VERSION"
else
    echo "⚠ Rust not found. Installing Rust..."
    
    # Download and install rustup
    echo "  Downloading and running rustup installer..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    
    # Source cargo env
    source "$HOME/.cargo/env"
    
    echo "✓ Rust installed successfully!"
fi

# Make sure cargo is in PATH for this session
if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
fi

echo ""

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Install Python Dependencies
# ═══════════════════════════════════════════════════════════════════

echo "━━━━ Step 3: Installing Python dependencies... ━━━━"

# Ensure pip is up to date
$PYTHON_CMD -m pip install --upgrade pip --quiet 2>/dev/null || true

# Install Python packages
if [ -f "local_requirements.txt" ]; then
    echo "  Installing from local_requirements.txt..."
    $PYTHON_CMD -m pip install -r local_requirements.txt --quiet
    echo "✓ Python dependencies installed"
elif [ -f "requirements.txt" ]; then
    echo "  Installing from requirements.txt..."
    $PYTHON_CMD -m pip install -r requirements.txt --quiet
    echo "✓ Python dependencies installed"
else
    echo "  No requirements file found, installing common dependencies..."
    $PYTHON_CMD -m pip install solana solders --quiet
    echo "✓ Common dependencies installed"
fi

echo ""

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Build Rust Components
# ═══════════════════════════════════════════════════════════════════

echo "━━━━ Step 4: Building Rust components... ━━━━"

# Check for secure_signer directory
if [ -d "secure_signer" ]; then
    echo "  Building secure_signer..."
    cd secure_signer
    cargo build --release
    cd ..
    echo "✓ secure_signer built successfully!"
fi

# Check for rust_signer directory (alternative name)
if [ -d "rust_signer" ]; then
    echo "  Building rust_signer..."
    cd rust_signer
    cargo build --release
    cd ..
    echo "✓ rust_signer built successfully!"
fi

echo ""

# ═══════════════════════════════════════════════════════════════════
# STEP 5: Verify Installation
# ═══════════════════════════════════════════════════════════════════

echo "━━━━ Step 5: Verifying installation... ━━━━"

ALL_GOOD=true

# Check Python
if command -v $PYTHON_CMD &> /dev/null; then
    PYTHON_VER=$($PYTHON_CMD --version)
    echo "✓ Python: $PYTHON_VER"
else
    echo "❌ Python verification failed"
    ALL_GOOD=false
fi

# Check Rust
if command -v cargo &> /dev/null; then
    CARGO_VER=$(cargo --version)
    echo "✓ Cargo: $CARGO_VER"
else
    echo "❌ Cargo verification failed"
    ALL_GOOD=false
fi

echo ""

# ═══════════════════════════════════════════════════════════════════
# COMPLETION
# ═══════════════════════════════════════════════════════════════════

if [ "$ALL_GOOD" = true ]; then
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              ✓ INSTALLATION COMPLETE!                         ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "You can now run the application with:"
    echo "  $PYTHON_CMD main.py"
    echo ""
    echo "Or run the quickstart script:"
    echo "  ./quickstart.sh"
    echo ""
    
    # Make quickstart executable if it exists
    if [ -f "quickstart.sh" ]; then
        chmod +x quickstart.sh
    fi
else
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              ⚠ INSTALLATION HAD ERRORS                        ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Please check the errors above and try again."
    exit 1
fi
