# Build Rust Secure Signer
# Run this script to compile the secure signing library

Write-Host "🔨 Building Rust Secure Signer..." -ForegroundColor Cyan
Write-Host ""

# Check if Rust is installed
if (!(Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Rust is not installed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Install Rust from: https://rustup.rs/" -ForegroundColor Yellow
    Write-Host "After installation, restart your terminal and run this script again." -ForegroundColor Yellow
    exit 1
}

# Check Rust version
Write-Host "✓ Rust installed:" -ForegroundColor Green
cargo --version
Write-Host ""

# Navigate to rust_signer directory
if (!(Test-Path "rust_signer")) {
    Write-Host "❌ rust_signer directory not found!" -ForegroundColor Red
    exit 1
}

Set-Location rust_signer

# Build release version
Write-Host "🔧 Compiling release build (this may take a few minutes)..." -ForegroundColor Cyan
cargo build --release

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Created files:" -ForegroundColor Cyan
    Write-Host "  • target\release\solana_secure_signer.dll" -ForegroundColor White
    Write-Host "  • target\release\solana-signer.exe" -ForegroundColor White
    Write-Host ""
    
    # Go back to project root
    Set-Location ..
    
    # Test the signer
    Write-Host "🧪 Testing Rust signer..." -ForegroundColor Cyan
    python check_signer.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "🎉 RUST SECURE SIGNER IS READY!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Your wallet now has enterprise-grade security:" -ForegroundColor Yellow
        Write-Host "  ✓ Private keys locked in RAM (no swap)" -ForegroundColor Green
        Write-Host "  ✓ Keys exist < 1ms (only during signing)" -ForegroundColor Green
        Write-Host "  ✓ Automatic memory zeroization" -ForegroundColor Green
        Write-Host "  ✓ Keys NEVER enter Python memory" -ForegroundColor Green
        Write-Host ""
        Write-Host "Run: python main.py" -ForegroundColor Cyan
    }
} else {
    Write-Host ""
    Write-Host "❌ Build failed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Common fixes:" -ForegroundColor Yellow
    Write-Host "  1. Update Rust: rustup update" -ForegroundColor White
    Write-Host "  2. Check Rust version: cargo --version (need 1.70+)" -ForegroundColor White
    Write-Host "  3. Clean and retry: cargo clean && cargo build --release" -ForegroundColor White
    
    Set-Location ..
    exit 1
}
