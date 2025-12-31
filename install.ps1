# ═══════════════════════════════════════════════════════════════════
#  COLDSTAR AUTO-INSTALLER (Windows/PowerShell)
#  One-command installation for all dependencies
# ═══════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║              COLDSTAR - AUTO INSTALLER                         ║" -ForegroundColor Cyan
Write-Host "║         Installing all dependencies automatically...           ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Check/Install Python
# ═══════════════════════════════════════════════════════════════════

Write-Host "━━━━ Step 1: Checking Python... ━━━━" -ForegroundColor Yellow

$pythonInstalled = $false
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python 3\.([7-9]|[1-9][0-9])") {
        Write-Host "✓ Python already installed: $pythonVersion" -ForegroundColor Green
        $pythonInstalled = $true
    }
} catch {
    # Python not found
}

if (-not $pythonInstalled) {
    Write-Host "⚠ Python not found. Installing Python..." -ForegroundColor Yellow
    
    # Check if winget is available
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  Using winget to install Python..." -ForegroundColor Cyan
        try {
            winget install Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
            Write-Host "✓ Python installed successfully!" -ForegroundColor Green
            
            # Refresh environment variables
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        } catch {
            Write-Host "❌ Failed to install Python via winget" -ForegroundColor Red
            Write-Host "Please install Python manually from: https://www.python.org/downloads/" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "❌ winget not available. Please install Python manually:" -ForegroundColor Red
        Write-Host "   Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "   Or install winget (Windows Package Manager) first" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Check/Install Rust
# ═══════════════════════════════════════════════════════════════════

Write-Host "━━━━ Step 2: Checking Rust/Cargo... ━━━━" -ForegroundColor Yellow

$rustInstalled = $false
try {
    $cargoVersion = cargo --version 2>&1
    Write-Host "✓ Rust/Cargo already installed: $cargoVersion" -ForegroundColor Green
    $rustInstalled = $true
} catch {
    # Rust not found
}

if (-not $rustInstalled) {
    Write-Host "⚠ Rust not found. Installing Rust..." -ForegroundColor Yellow
    
    # Check if winget is available for Rust installation
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  Using winget to install Rust..." -ForegroundColor Cyan
        try {
            winget install Rustlang.Rustup --silent --accept-source-agreements --accept-package-agreements
            Write-Host "✓ Rustup installed successfully!" -ForegroundColor Green
            
            # Refresh environment variables
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            
            # Add cargo to current session path
            $env:Path += ";$env:USERPROFILE\.cargo\bin"
            
        } catch {
            Write-Host "❌ Failed to install Rust via winget" -ForegroundColor Red
            Write-Host "Trying alternative installation method..." -ForegroundColor Yellow
            
            # Download and run rustup-init.exe
            $rustupUrl = "https://win.rustup.rs/x86_64"
            $rustupPath = "$env:TEMP\rustup-init.exe"
            
            Write-Host "  Downloading rustup-init.exe..." -ForegroundColor Cyan
            Invoke-WebRequest -Uri $rustupUrl -OutFile $rustupPath
            
            Write-Host "  Running rustup installer..." -ForegroundColor Cyan
            Start-Process -FilePath $rustupPath -ArgumentList "-y" -Wait -NoNewWindow
            
            # Add cargo to path
            $env:Path += ";$env:USERPROFILE\.cargo\bin"
            
            Write-Host "✓ Rust installed successfully!" -ForegroundColor Green
        }
    } else {
        # Fallback to direct download
        Write-Host "  Downloading rustup installer..." -ForegroundColor Cyan
        $rustupUrl = "https://win.rustup.rs/x86_64"
        $rustupPath = "$env:TEMP\rustup-init.exe"
        
        Invoke-WebRequest -Uri $rustupUrl -OutFile $rustupPath
        
        Write-Host "  Running rustup installer..." -ForegroundColor Cyan
        Start-Process -FilePath $rustupPath -ArgumentList "-y" -Wait -NoNewWindow
        
        # Add cargo to path
        $env:Path += ";$env:USERPROFILE\.cargo\bin"
        
        Write-Host "✓ Rust installed successfully!" -ForegroundColor Green
    }
}

Write-Host ""

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Install Python Dependencies
# ═══════════════════════════════════════════════════════════════════

Write-Host "━━━━ Step 3: Installing Python dependencies... ━━━━" -ForegroundColor Yellow

# Check if pip is available
try {
    python -m pip --version | Out-Null
    Write-Host "✓ pip is available" -ForegroundColor Green
} catch {
    Write-Host "  Installing pip..." -ForegroundColor Cyan
    python -m ensurepip --upgrade
}

# Install Python packages
if (Test-Path "local_requirements.txt") {
    Write-Host "  Installing from local_requirements.txt..." -ForegroundColor Cyan
    python -m pip install -r local_requirements.txt --quiet
    Write-Host "✓ Python dependencies installed" -ForegroundColor Green
} elseif (Test-Path "requirements.txt") {
    Write-Host "  Installing from requirements.txt..." -ForegroundColor Cyan
    python -m pip install -r requirements.txt --quiet
    Write-Host "✓ Python dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  No requirements file found, installing common dependencies..." -ForegroundColor Cyan
    python -m pip install solana solders --quiet
    Write-Host "✓ Common dependencies installed" -ForegroundColor Green
}

Write-Host ""

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Build Rust Components
# ═══════════════════════════════════════════════════════════════════

Write-Host "━━━━ Step 4: Building Rust components... ━━━━" -ForegroundColor Yellow

# Check for secure_signer directory
if (Test-Path "secure_signer") {
    Write-Host "  Building secure_signer..." -ForegroundColor Cyan
    Push-Location secure_signer
    cargo build --release
    Pop-Location
    Write-Host "✓ secure_signer built successfully!" -ForegroundColor Green
}

# Check for rust_signer directory (alternative name)
if (Test-Path "rust_signer") {
    Write-Host "  Building rust_signer..." -ForegroundColor Cyan
    Push-Location rust_signer
    cargo build --release
    Pop-Location
    Write-Host "✓ rust_signer built successfully!" -ForegroundColor Green
}

Write-Host ""

# ═══════════════════════════════════════════════════════════════════
# STEP 5: Verify Installation
# ═══════════════════════════════════════════════════════════════════

Write-Host "━━━━ Step 5: Verifying installation... ━━━━" -ForegroundColor Yellow

$allGood = $true

# Check Python
try {
    $pythonVer = python --version
    Write-Host "✓ Python: $pythonVer" -ForegroundColor Green
} catch {
    Write-Host "❌ Python verification failed" -ForegroundColor Red
    $allGood = $false
}

# Check Rust
try {
    $cargoVer = cargo --version
    Write-Host "✓ Cargo: $cargoVer" -ForegroundColor Green
} catch {
    Write-Host "❌ Cargo verification failed" -ForegroundColor Red
    $allGood = $false
}

Write-Host ""

# ═══════════════════════════════════════════════════════════════════
# COMPLETION
# ═══════════════════════════════════════════════════════════════════

if ($allGood) {
    Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║              ✓ INSTALLATION COMPLETE!                         ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now run the application with:" -ForegroundColor Cyan
    Write-Host "  python main.py" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Or run the quickstart script:" -ForegroundColor Cyan
    Write-Host "  .\quickstart.ps1" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Red
    Write-Host "║              ⚠ INSTALLATION HAD ERRORS                        ║" -ForegroundColor Red
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check the errors above and try again." -ForegroundColor Yellow
    exit 1
}
