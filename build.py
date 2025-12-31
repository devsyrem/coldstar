#!/usr/bin/env python3
"""
Build Script for Solana Cold Wallet
Handles:
1. Installing Python dependencies from local_requirements.txt
2. Building the Rust secure signer library
"""

import subprocess
import sys
import os
from pathlib import Path


def print_step(msg: str):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def run_command(cmd: list, cwd: str = None, check: bool = True) -> bool:
    """Run a command and return success status"""
    try:
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            capture_output=False,
            text=True
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"Command not found: {cmd[0]}")
        return False


def install_python_dependencies() -> bool:
    """Install Python dependencies from local_requirements.txt"""
    print_step("Installing Python Dependencies")
    
    requirements_file = Path("local_requirements.txt")
    if not requirements_file.exists():
        print("Warning: local_requirements.txt not found")
        return True
    
    return run_command([
        sys.executable, "-m", "pip", "install", 
        "-r", "local_requirements.txt",
        "--quiet"
    ])


def check_rust_installed() -> bool:
    """Check if Rust/Cargo is installed"""
    try:
        result = subprocess.run(
            ["cargo", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"Found: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    return False


def install_rust() -> bool:
    """Attempt to install Rust using rustup"""
    print("Rust not found. Attempting to install...")
    
    if sys.platform == "win32":
        print("Please install Rust manually from: https://rustup.rs/")
        return False
    
    try:
        result = subprocess.run(
            ["sh", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
            check=True
        )
        os.environ["PATH"] = f"{Path.home()}/.cargo/bin:" + os.environ.get("PATH", "")
        return True
    except subprocess.CalledProcessError:
        print("Failed to install Rust. Please install manually from: https://rustup.rs/")
        return False


def build_rust_signer(release: bool = True) -> bool:
    """Build the Rust secure signer library"""
    print_step("Building Rust Secure Signer")
    
    signer_dir = Path("secure_signer")
    if not signer_dir.exists():
        print(f"Error: {signer_dir} directory not found")
        return False
    
    if not (signer_dir / "Cargo.toml").exists():
        print(f"Error: Cargo.toml not found in {signer_dir}")
        return False
    
    if not check_rust_installed():
        if not install_rust():
            return False
    
    cmd = ["cargo", "build", "--features", "ffi"]
    if release:
        cmd.append("--release")
    
    success = run_command(cmd, cwd=str(signer_dir))
    
    if success:
        target_dir = "release" if release else "debug"
        binary_path = signer_dir / "target" / target_dir / "solana-signer"
        lib_path = signer_dir / "target" / target_dir / "libsecure_signer.so"
        
        if sys.platform == "darwin":
            lib_path = signer_dir / "target" / target_dir / "libsecure_signer.dylib"
        elif sys.platform == "win32":
            lib_path = signer_dir / "target" / target_dir / "secure_signer.dll"
            binary_path = signer_dir / "target" / target_dir / "solana-signer.exe"
        
        print(f"\nBuild successful!")
        if binary_path.exists():
            print(f"  Binary: {binary_path}")
        if lib_path.exists():
            print(f"  Library: {lib_path}")
    
    return success


def run_rust_tests() -> bool:
    """Run Rust tests with permissive memory mode"""
    print_step("Running Rust Tests")
    
    signer_dir = Path("secure_signer")
    if not signer_dir.exists():
        print("Skipping tests: secure_signer directory not found")
        return True
    
    env = os.environ.copy()
    env["SIGNER_ALLOW_INSECURE_MEMORY"] = "1"
    
    try:
        result = subprocess.run(
            ["cargo", "test", "--features", "ffi"],
            cwd=str(signer_dir),
            env=env,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        print("cargo not found, skipping tests")
        return True


def build_all(release: bool = True, run_tests: bool = False) -> bool:
    """Run the complete build process"""
    print("\n" + "="*60)
    print("  SOLANA COLD WALLET BUILD")
    print("="*60)
    
    if not install_python_dependencies():
        print("\nWarning: Some Python dependencies may not have installed correctly")
    
    if not build_rust_signer(release=release):
        print("\nError: Rust build failed")
        return False
    
    if run_tests:
        if not run_rust_tests():
            print("\nWarning: Some tests failed")
    
    print_step("Build Complete!")
    print("You can now run: python main.py")
    
    return True


def is_built() -> bool:
    """Check if the Rust signer is already built"""
    signer_dir = Path("secure_signer")
    
    # Library name is based on crate name (solana_secure_signer)
    if sys.platform == "darwin":
        lib_name = "libsolana_secure_signer.dylib"
    elif sys.platform == "win32":
        lib_name = "solana_secure_signer.dll"
    else:
        lib_name = "libsolana_secure_signer.so"
    
    release_lib = signer_dir / "target" / "release" / lib_name
    debug_lib = signer_dir / "target" / "debug" / lib_name
    
    return release_lib.exists() or debug_lib.exists()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Build Solana Cold Wallet")
    parser.add_argument("--debug", action="store_true", help="Build in debug mode")
    parser.add_argument("--test", action="store_true", help="Run tests after building")
    parser.add_argument("--check", action="store_true", help="Only check if build exists")
    
    args = parser.parse_args()
    
    if args.check:
        if is_built():
            print("Rust signer is built")
            sys.exit(0)
        else:
            print("Rust signer needs to be built")
            sys.exit(1)
    
    success = build_all(release=not args.debug, run_tests=args.test)
    sys.exit(0 if success else 1)
