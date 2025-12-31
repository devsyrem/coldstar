#!/bin/bash
# Quick start script for Solana Secure Signer

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         SOLANA SECURE SIGNER - QUICK START SETUP              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check for Rust
if ! command -v cargo &> /dev/null; then
    echo "❌ Rust/Cargo not found!"
    echo ""
    echo "Please install Rust first:"
    echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo ""
    exit 1
fi

echo "✓ Rust found: $(rustc --version)"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found!"
    echo "Please install Python 3.7+"
    exit 1
fi

echo "✓ Python found: $(python3 --version)"
echo ""

# Build the Rust library
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Building Rust library (release mode)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd rust_signer
cargo build --release

echo ""
echo "✓ Rust library built successfully!"
echo ""

# Run Rust tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Running Rust tests..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cargo test

echo ""
echo "✓ All Rust tests passed!"
echo ""

cd ..

# Run Python example
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Running Python integration example..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 python_signer_example.py

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Setup complete! All tests passed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo ""
echo "  1. Review the integration guide:"
echo "     cat INTEGRATION_GUIDE.md"
echo ""
echo "  2. Review the security model:"
echo "     cat rust_signer/SECURITY.md"
echo ""
echo "  3. Integrate with your Python CLI:"
echo "     See INTEGRATION_GUIDE.md for step-by-step instructions"
echo ""
echo "  4. Create an encrypted key container:"
echo "     python3 -c 'from python_signer_example import SolanaSecureSigner; ...'"
echo ""
echo "Files created:"
echo "  • rust_signer/target/release/libsolana_secure_signer.* (FFI library)"
echo "  • rust_signer/target/release/solana-signer (CLI binary)"
echo ""
echo "Documentation:"
echo "  • README.md                 - Overview and usage"
echo "  • INTEGRATION_GUIDE.md      - Step-by-step integration"
echo "  • rust_signer/SECURITY.md   - Security model details"
echo "  • rust_signer/README.md     - Rust library documentation"
echo ""
