"""
Security Validation Module

Provides input validation and sanitization functions to prevent
security vulnerabilities like command injection, path traversal, etc.

B - Love U 3000
"""

import os
import re
from pathlib import Path
from typing import Tuple, Optional

# Constants for validation
MIN_PASSWORD_LENGTH = 12
MAX_BALANCE_SOL = 1_000_000_000  # 1 billion SOL (way more than total supply)
LAMPORTS_PER_SOL = 1_000_000_000


def validate_device_path(path: str, platform: str = None) -> Tuple[bool, str]:
    """
    Validate device path to prevent injection attacks.
    
    Args:
        path: Device path to validate
        platform: OS platform ('Linux', 'Darwin', 'Windows')
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path:
        return False, "Device path cannot be empty"
    
    # Detect platform if not provided
    if platform is None:
        import platform as plat
        platform = plat.system()
    
    # Prevent path traversal
    if '..' in path or '//' in path:
        return False, "Invalid device path: contains path traversal sequences"
    
    # Prevent null bytes
    if '\x00' in path:
        return False, "Invalid device path: contains null bytes"
    
    # Platform-specific validation
    if platform == 'Linux' or platform == 'Darwin':
        # Unix-like systems: /dev/* paths only
        if not path.startswith('/dev/'):
            return False, "Invalid device path: must start with /dev/"
        
        # Only allow expected device name patterns
        # Linux: /dev/sda, /dev/sda1, /dev/sdb, etc.
        # macOS: /dev/disk2, /dev/disk2s1, etc.
        if not re.match(r'^/dev/(sd[a-z]\d*|disk\d+s?\d*|mmcblk\d+p?\d*)$', path):
            return False, "Invalid device path: unexpected device name format"
        
        # Resolve symlinks and verify still in /dev
        try:
            real_path = os.path.realpath(path)
            if not real_path.startswith('/dev/'):
                return False, "Invalid device path: resolves outside /dev/"
        except Exception:
            return False, "Invalid device path: cannot resolve"
            
    elif platform == 'Windows':
        # Windows: Drive letters only
        if not re.match(r'^[A-Z]:\\?$', path, re.IGNORECASE):
            return False, "Invalid device path: must be a drive letter (e.g., D:)"
    
    return True, ""


def validate_mount_point(mount_point: str, platform: str = None) -> Tuple[bool, str]:
    """
    Validate mount point path to prevent injection.
    
    Args:
        mount_point: Mount point path to validate
        platform: OS platform ('Linux', 'Darwin', 'Windows')
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not mount_point:
        return False, "Mount point cannot be empty"
    
    # Detect platform if not provided
    if platform is None:
        import platform as plat
        platform = plat.system()
    
    # Prevent path traversal
    if '..' in mount_point:
        return False, "Invalid mount point: contains path traversal"
    
    # Prevent null bytes
    if '\x00' in mount_point:
        return False, "Invalid mount point: contains null bytes"
    
    # Convert to Path for validation
    try:
        mount_path = Path(mount_point).resolve()
    except Exception:
        return False, "Invalid mount point: cannot resolve path"
    
    # Platform-specific validation
    if platform == 'Linux':
        # Linux: typically /media, /mnt, or /run/media
        allowed_prefixes = ['/media/', '/mnt/', '/run/media/']
        if not any(str(mount_path).startswith(prefix) for prefix in allowed_prefixes):
            return False, f"Invalid mount point: must be under /media/, /mnt/, or /run/media/"
    
    elif platform == 'Darwin':
        # macOS: /Volumes only
        if not str(mount_path).startswith('/Volumes/'):
            return False, "Invalid mount point: must be under /Volumes/"
    
    elif platform == 'Windows':
        # Windows: Drive letter paths
        if not re.match(r'^[A-Z]:\\', str(mount_path), re.IGNORECASE):
            return False, "Invalid mount point: must be a drive path (e.g., D:\\)"
    
    return True, ""


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validate password meets security requirements.
    
    Requirements:
    - At least 12 characters long
    - Contains uppercase letter
    - Contains lowercase letter
    - Contains number
    - Not a common password
    
    Args:
        password: Password to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not password:
        return False, "Password cannot be empty"
    
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    # Check against common passwords
    common_passwords = {
        'password', '12345678', '123456789', '1234567890',
        'qwerty', 'abc123', 'password123', 'admin',
        'letmein', 'welcome', 'monkey', '1234',
        'password1', '123456', 'qwerty123'
    }
    
    if password.lower() in common_passwords:
        return False, "Password is too common. Please choose a stronger password"
    
    return True, ""


def validate_solana_address(address: str) -> Tuple[bool, str]:
    """
    Validate Solana public key address format.
    
    Args:
        address: Base58-encoded Solana address
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not address:
        return False, "Address cannot be empty"
    
    # Solana addresses are base58-encoded 32-byte public keys
    # They are typically 32-44 characters long
    if len(address) < 32 or len(address) > 44:
        return False, "Invalid address length"
    
    # Check for valid base58 characters only
    valid_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
    if not all(c in valid_chars for c in address):
        return False, "Invalid characters in address (must be base58)"
    
    # Try to parse with solders library for full validation
    try:
        from solders.pubkey import Pubkey
        Pubkey.from_string(address)
        return True, ""
    except Exception as e:
        return False, f"Invalid Solana address format: {str(e)}"


def validate_balance_value(lamports: int) -> Tuple[bool, str]:
    """
    Validate balance value is within reasonable range.
    
    Args:
        lamports: Balance in lamports
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(lamports, (int, float)):
        return False, "Balance must be a number"
    
    if lamports < 0:
        return False, "Balance cannot be negative"
    
    # Solana's max supply is ~500M SOL, use 1B as safe upper bound
    max_lamports = MAX_BALANCE_SOL * LAMPORTS_PER_SOL
    if lamports > max_lamports:
        return False, f"Balance exceeds maximum possible value ({MAX_BALANCE_SOL} SOL)"
    
    return True, ""


def validate_amount_sol(amount: float) -> Tuple[bool, str]:
    """
    Validate transfer amount is reasonable.
    
    Args:
        amount: Amount in SOL
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(amount, (int, float)):
        return False, "Amount must be a number"
    
    if amount <= 0:
        return False, "Amount must be greater than 0"
    
    if amount > MAX_BALANCE_SOL:
        return False, f"Amount exceeds maximum ({MAX_BALANCE_SOL} SOL)"
    
    # Check for reasonable precision (max 9 decimal places for lamports)
    lamports = int(amount * LAMPORTS_PER_SOL)
    reconstructed_amount = lamports / LAMPORTS_PER_SOL
    if abs(amount - reconstructed_amount) > 1e-9:
        return False, "Amount has too many decimal places (max 9)"
    
    return True, ""


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks.
    
    Args:
        filename: Original filename
        max_length: Maximum allowed length
    
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed"
    
    # Remove path components
    filename = os.path.basename(filename)
    
    # Remove null bytes
    filename = filename.replace('\x00', '')
    
    # Replace path separators
    filename = filename.replace('/', '_').replace('\\', '_')
    
    # Remove or replace problematic characters
    # Keep alphanumeric, dots, dashes, underscores
    filename = re.sub(r'[^\w\.\-]', '_', filename)
    
    # Prevent hidden files
    if filename.startswith('.'):
        filename = '_' + filename[1:]
    
    # Limit length
    if len(filename) > max_length:
        # Keep extension if present
        name, ext = os.path.splitext(filename)
        name = name[:max_length - len(ext) - 1]
        filename = name + ext
    
    # Ensure not empty after sanitization
    if not filename or filename == '.':
        filename = 'unnamed'
    
    return filename


def validate_rpc_url(url: str) -> Tuple[bool, str]:
    """
    Validate RPC URL format.
    
    Args:
        url: RPC URL to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "RPC URL cannot be empty"
    
    # Must be HTTP or HTTPS
    if not (url.startswith('http://') or url.startswith('https://')):
        return False, "RPC URL must start with http:// or https://"
    
    # Basic URL validation
    import re
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:[A-Za-z0-9\-]+\.)*[A-Za-z0-9\-]+'  # domain
        r'(?:\:[0-9]{1,5})?'  # optional port
        r'(?:/.*)?$'  # optional path
    )
    
    if not url_pattern.match(url):
        return False, "Invalid RPC URL format"
    
    # Warn about HTTP (not HTTPS)
    if url.startswith('http://') and not url.startswith('http://localhost') and not url.startswith('http://127.0.0.1'):
        return True, "Warning: Using unencrypted HTTP connection (use HTTPS for security)"
    
    return True, ""
