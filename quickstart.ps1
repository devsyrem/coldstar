# Quick start script for Solana Secure Signer (Windows/PowerShell)

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         SOLANA SECURE SIGNER - QUICK START SETUP              ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check for Rust
try {
    $rustVersion = cargo --version
    Write-Host "✓ Rust found: $rustVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Rust/Cargo not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Rust first:"
    Write-Host "  Visit: https://rustup.rs/"
    Write-Host "  Or run: winget install Rustlang.Rustup"
    Write-Host ""
    exit 1
}

# Check for Python
try {
    $pythonVersion = python --version
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.7+"
    exit 1
}

Write-Host ""

# Build the Rust library
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 1: Building Rust library (release mode)..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

Push-Location rust_signer
cargo build --release

Write-Host ""
Write-Host "✓ Rust library built successfully!" -ForegroundColor Green
Write-Host ""

# Run Rust tests
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 2: Running Rust tests..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

cargo test

Write-Host ""
Write-Host "✓ All Rust tests passed!" -ForegroundColor Green
Write-Host ""

Pop-Location

# Run Python example
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 3: Running Python integration example..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

python python_signer_example.py

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "✓ Setup complete! All tests passed!" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Review the integration guide:"
Write-Host "     Get-Content INTEGRATION_GUIDE.md"
Write-Host ""
Write-Host "  2. Review the security model:"
Write-Host "     Get-Content rust_signer\SECURITY.md"
Write-Host ""
Write-Host "  3. Integrate with your Python CLI:"
Write-Host "     See INTEGRATION_GUIDE.md for step-by-step instructions"
Write-Host ""
Write-Host "Files created:" -ForegroundColor Cyan
Write-Host "  • rust_signer\target\release\solana_secure_signer.dll (FFI library)"
Write-Host "  • rust_signer\target\release\solana-signer.exe (CLI binary)"
Write-Host ""
Write-Host "Documentation:" -ForegroundColor Cyan
Write-Host "  • README.md                   - Overview and usage"
Write-Host "  • INTEGRATION_GUIDE.md        - Step-by-step integration"
Write-Host "  • rust_signer\SECURITY.md     - Security model details"
Write-Host "  • rust_signer\README.md       - Rust library documentation"
Write-Host ""
