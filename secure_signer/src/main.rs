//! Solana Secure Signer CLI
//!
//! A command-line interface for the secure signing core.
//! Can be used as a subprocess from Python or other languages.
//!
//! # Usage
//!
//! ```bash
//! # Create encrypted container
//! solana-signer create-container --key <base58_key> --passphrase <pass>
//!
//! # Sign a transaction
//! solana-signer sign --container <json_file> --passphrase <pass> --transaction <base64>
//!
//! # One-shot mode (stdin/stdout)
//! echo '{"action":"sign",...}' | solana-signer --stdin
//! ```
//!
//! # Security
//!
//! - Passphrases can be provided via environment variable SIGNER_PASSPHRASE
//! - The --stdin mode is preferred for automation to avoid command-line leaks
//! - Memory is locked and zeroized for all operations

use clap::{Parser, Subcommand};
use serde::{Deserialize, Serialize};
use std::io::{self, BufRead, Write};

use solana_secure_signer::{
    create_encrypted_key_container, decrypt_and_sign, sign_transaction, EncryptedKeyContainer,
    SignerError,
};

#[derive(Parser)]
#[command(name = "solana-signer")]
#[command(about = "Secure signing core for Solana transactions")]
#[command(version)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,

    /// Read JSON commands from stdin (one-shot mode)
    #[arg(long)]
    stdin: bool,

    /// Output format: json or text
    #[arg(long, default_value = "json")]
    format: String,
}

#[derive(Subcommand)]
enum Commands {
    /// Create an encrypted key container
    CreateContainer {
        /// Base58-encoded private key (32 or 64 bytes)
        #[arg(long, env = "SIGNER_PRIVATE_KEY")]
        key: String,

        /// Passphrase for encryption
        #[arg(long, env = "SIGNER_PASSPHRASE")]
        passphrase: String,

        /// Output file (default: stdout)
        #[arg(long, short)]
        output: Option<String>,
    },

    /// Sign a transaction using an encrypted container
    Sign {
        /// Path to encrypted container JSON file, or "-" for stdin
        #[arg(long)]
        container: String,

        /// Passphrase for decryption
        #[arg(long, env = "SIGNER_PASSPHRASE")]
        passphrase: String,

        /// Base64-encoded unsigned transaction
        #[arg(long)]
        transaction: String,
    },

    /// Sign directly with a private key (less secure)
    SignDirect {
        /// Base58-encoded private key
        #[arg(long, env = "SIGNER_PRIVATE_KEY")]
        key: String,

        /// Base64-encoded message to sign
        #[arg(long)]
        message: String,
    },

    /// Check system capabilities
    Check,
}

/// JSON input format for stdin mode
#[derive(Deserialize)]
#[serde(tag = "action")]
enum StdinCommand {
    #[serde(rename = "create_container")]
    CreateContainer {
        private_key: String,
        passphrase: String,
    },
    #[serde(rename = "sign")]
    Sign {
        container: String,
        passphrase: String,
        transaction: String,
    },
    #[serde(rename = "sign_direct")]
    SignDirect { private_key: String, message: String },
    #[serde(rename = "check")]
    Check,
}

/// JSON output format
#[derive(Serialize)]
struct Output {
    success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

impl Output {
    fn success(data: serde_json::Value) -> Self {
        Self {
            success: true,
            data: Some(data),
            error: None,
        }
    }

    fn error(msg: &str) -> Self {
        Self {
            success: false,
            data: None,
            error: Some(msg.to_string()),
        }
    }
}

fn main() {
    let cli = Cli::parse();

    if cli.stdin {
        run_stdin_mode();
        return;
    }

    let result = match cli.command {
        Some(Commands::CreateContainer {
            key,
            passphrase,
            output,
        }) => handle_create_container(&key, &passphrase, output.as_deref()),

        Some(Commands::Sign {
            container,
            passphrase,
            transaction,
        }) => handle_sign(&container, &passphrase, &transaction),

        Some(Commands::SignDirect { key, message }) => handle_sign_direct(&key, &message),

        Some(Commands::Check) => handle_check(),

        None => {
            eprintln!("No command specified. Use --help for usage.");
            std::process::exit(1);
        }
    };

    // Output result
    match result {
        Ok(output) => {
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
        }
        Err(e) => {
            let output = Output::error(&e.to_string());
            eprintln!("{}", serde_json::to_string_pretty(&output).unwrap());
            std::process::exit(1);
        }
    }
}

fn run_stdin_mode() {
    let stdin = io::stdin();
    let mut stdout = io::stdout();

    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(e) => {
                let output = Output::error(&format!("Read error: {}", e));
                println!("{}", serde_json::to_string(&output).unwrap());
                continue;
            }
        };

        if line.trim().is_empty() {
            continue;
        }

        let result = process_stdin_command(&line);
        let output_str = serde_json::to_string(&result).unwrap();
        writeln!(stdout, "{}", output_str).unwrap();
        stdout.flush().unwrap();
    }
}

fn process_stdin_command(json: &str) -> Output {
    let command: StdinCommand = match serde_json::from_str(json) {
        Ok(c) => c,
        Err(e) => return Output::error(&format!("Invalid JSON: {}", e)),
    };

    let result = match command {
        StdinCommand::CreateContainer {
            private_key,
            passphrase,
        } => handle_create_container(&private_key, &passphrase, None),

        StdinCommand::Sign {
            container,
            passphrase,
            transaction,
        } => handle_sign_inline(&container, &passphrase, &transaction),

        StdinCommand::SignDirect {
            private_key,
            message,
        } => handle_sign_direct(&private_key, &message),

        StdinCommand::Check => handle_check(),
    };

    match result {
        Ok(output) => output,
        Err(e) => Output::error(&e.to_string()),
    }
}

fn handle_create_container(
    key_b58: &str,
    passphrase: &str,
    output_file: Option<&str>,
) -> Result<Output, SignerError> {
    // Decode the private key
    let private_key = bs58::decode(key_b58)
        .into_vec()
        .map_err(|e| SignerError::Base58Error(e.to_string()))?;

    // Create the container
    let container_json = create_encrypted_key_container(&private_key, passphrase)?;

    // Output
    if let Some(path) = output_file {
        std::fs::write(path, &container_json)?;
        Ok(Output::success(serde_json::json!({
            "message": format!("Container written to {}", path),
            "path": path
        })))
    } else {
        let container: EncryptedKeyContainer = serde_json::from_str(&container_json)?;
        Ok(Output::success(serde_json::to_value(&container)?))
    }
}

fn handle_sign(
    container_path: &str,
    passphrase: &str,
    transaction_b64: &str,
) -> Result<Output, SignerError> {
    // Read container
    let container_json = if container_path == "-" {
        let mut input = String::new();
        io::stdin()
            .read_line(&mut input)
            .map_err(|e| SignerError::IoError(e.to_string()))?;
        input
    } else {
        std::fs::read_to_string(container_path)?
    };

    handle_sign_inline(&container_json, passphrase, transaction_b64)
}

fn handle_sign_inline(
    container_json: &str,
    passphrase: &str,
    transaction_b64: &str,
) -> Result<Output, SignerError> {
    // Decode transaction
    let transaction_bytes = base64::Engine::decode(
        &base64::engine::general_purpose::STANDARD,
        transaction_b64,
    )
    .map_err(|e| SignerError::Base64Error(e.to_string()))?;

    // Sign
    let result = decrypt_and_sign(container_json, passphrase, &transaction_bytes)?;

    Ok(Output::success(serde_json::to_value(&result)?))
}

fn handle_sign_direct(key_b58: &str, message_b64: &str) -> Result<Output, SignerError> {
    // Decode inputs
    let private_key = bs58::decode(key_b58)
        .into_vec()
        .map_err(|e| SignerError::Base58Error(e.to_string()))?;

    let message = base64::Engine::decode(&base64::engine::general_purpose::STANDARD, message_b64)
        .map_err(|e| SignerError::Base64Error(e.to_string()))?;

    // Sign
    let result = sign_transaction(&private_key, &message)?;

    Ok(Output::success(serde_json::to_value(&result)?))
}

fn handle_check() -> Result<Output, SignerError> {
    use solana_secure_signer::SecureBuffer;

    let buffer = SecureBuffer::new(64)?;
    let mlock_supported = buffer.is_locked();

    Ok(Output::success(serde_json::json!({
        "version": solana_secure_signer::VERSION,
        "mlock_supported": mlock_supported,
        "platform": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
    })))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stdin_command_parsing() {
        let json = r#"{"action":"check"}"#;
        let cmd: StdinCommand = serde_json::from_str(json).unwrap();
        assert!(matches!(cmd, StdinCommand::Check));
    }
}
