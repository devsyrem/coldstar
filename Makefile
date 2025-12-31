# Makefile for Solana Secure Signer

.PHONY: all build release test clean install help

# Default target
all: build

# Build in debug mode
build:
	@echo "Building in debug mode..."
	cd rust_signer && cargo build

# Build in release mode (optimized)
release:
	@echo "Building in release mode..."
	cd rust_signer && cargo build --release
	@echo ""
	@echo "✓ Build complete!"
	@echo "  Library: rust_signer/target/release/libsolana_secure_signer.*"
	@echo "  Binary:  rust_signer/target/release/solana-signer"

# Run tests
test:
	@echo "Running Rust tests..."
	cd rust_signer && cargo test
	@echo ""
	@echo "Running Python example..."
	python python_signer_example.py

# Run tests with coverage
coverage:
	@echo "Running tests with coverage..."
	cd rust_signer && cargo tarpaulin --out Html
	@echo "Coverage report: rust_signer/tarpaulin-report.html"

# Run clippy (linter)
lint:
	@echo "Running clippy..."
	cd rust_signer && cargo clippy -- -D warnings

# Format code
format:
	@echo "Formatting code..."
	cd rust_signer && cargo fmt

# Check formatting
check-format:
	@echo "Checking code formatting..."
	cd rust_signer && cargo fmt -- --check

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	cd rust_signer && cargo clean
	rm -rf **/__pycache__
	rm -f *.so *.dylib *.dll

# Install (copy binaries to system)
install: release
	@echo "Installing binaries..."
	@echo "Note: This requires appropriate permissions"
	install -m 755 rust_signer/target/release/solana-signer /usr/local/bin/ || \
		echo "Failed to install. Try: sudo make install"

# Development workflow
dev: format lint test
	@echo "✓ Development checks passed!"

# CI workflow
ci: check-format lint test
	@echo "✓ CI checks passed!"

# Help
help:
	@echo "Solana Secure Signer - Build Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  build        - Build in debug mode"
	@echo "  release      - Build optimized release version"
	@echo "  test         - Run all tests (Rust + Python)"
	@echo "  coverage     - Generate test coverage report"
	@echo "  lint         - Run clippy linter"
	@echo "  format       - Format code with rustfmt"
	@echo "  check-format - Check if code is formatted"
	@echo "  clean        - Remove build artifacts"
	@echo "  install      - Install binaries to /usr/local/bin"
	@echo "  dev          - Format, lint, and test (development workflow)"
	@echo "  ci           - Check format, lint, and test (CI workflow)"
	@echo "  help         - Show this help message"
