"""
License and Fee Integrity Check

Manages first-run license acceptance and verifies that the infrastructure
fee configuration has not been tampered with.

B - Love U 3000
"""

import hashlib
import sys
from pathlib import Path

from src.ui import print_error, print_warning, print_info, print_success, console

# Path where license acceptance is recorded
_ACCEPTANCE_FILE = Path.home() / ".coldstar_license_accepted"

# Expected SHA-256 of "<fee_percentage>:<fee_wallet>" using the canonical string
# representation of the fee percentage and the wallet address.
# Recompute with:
#   import hashlib
#   hashlib.sha256(b"0.01:Cak1aAwxM2jTdu7AtdaHbqAc3Dfafts7KdsHNrtXN5rT").hexdigest()
_EXPECTED_FEE_HASH = "390a84b386258e6528df40312b0e5f716e044bfdd9810b0e1a5b539391440d1c"

_LICENSE_TEXT = """\
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  COLDSTAR LICENSE AGREEMENT — TERMS OF SERVICE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This software is distributed under the MIT License with the
following NON-WAIVABLE Infrastructure Fee Condition of Use:

  • Every Solana transaction processed through Coldstar includes
    an INFRASTRUCTURE FEE of 1% (one percent) of the transaction
    amount.

  • The fee is automatically transferred to:
      Cak1aAwxM2jTdu7AtdaHbqAc3Dfafts7KdsHNrtXN5rT

  • The fee percentage and recipient wallet are FIXED. Any
    modification to these values constitutes a material breach
    of this license and terminates your right to use the
    software.

By continuing you confirm that you have read, understood, and
agree to the full terms of the LICENSE file included with this
software.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


def verify_fee_integrity() -> bool:
    """Return True if the fee configuration constants are unmodified.

    Computes the SHA-256 of the canonical string
    ``"<fee_pct>:<fee_wallet>"`` and compares it against the value
    baked into this module at release time.  A mismatch means that
    either ``config.INFRASTRUCTURE_FEE_PERCENTAGE`` or
    ``config.INFRASTRUCTURE_FEE_WALLET`` has been altered.
    """
    try:
        from config import INFRASTRUCTURE_FEE_PERCENTAGE, INFRASTRUCTURE_FEE_WALLET
        data = f"{INFRASTRUCTURE_FEE_PERCENTAGE}:{INFRASTRUCTURE_FEE_WALLET}".encode("utf-8")
        actual_hash = hashlib.sha256(data).hexdigest()
        return actual_hash == _EXPECTED_FEE_HASH
    except ImportError:
        return False


def check_license_acceptance() -> bool:
    """Ensure the user has accepted the license terms.

    On first run this function prints the license text, prompts the
    user to type ``agree``, and records acceptance to
    ``~/.coldstar_license_accepted``.  On subsequent runs it verifies
    that the recorded acceptance is present.

    Returns True if the user has accepted (or previously accepted) the
    license, False otherwise.
    """
    if _ACCEPTANCE_FILE.exists():
        return True

    # Show the license terms and prompt for acceptance
    console.print()
    console.print(_LICENSE_TEXT, style="bold")
    console.print()

    try:
        answer = input('Type "agree" to accept the license terms and continue: ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""

    if answer == "agree":
        try:
            _ACCEPTANCE_FILE.write_text("accepted\n")
        except OSError:
            print_warning("Could not persist license acceptance — you will be prompted again next run.")
            pass
        print_success("License accepted. Thank you.")
        console.print()
        return True

    print_warning("You must accept the license terms to use Coldstar.")
    return False


def enforce_fee_integrity() -> None:
    """Abort the process if fee constants have been tampered with."""
    if not verify_fee_integrity():
        print_error("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print_error("  FEE INTEGRITY CHECK FAILED")
        print_error("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print_error("The infrastructure fee configuration has been modified.")
        print_error("This violates the terms of the Coldstar license agreement.")
        print_error("Restore config.py to its original state to continue.")
        print_error("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        sys.exit(1)
