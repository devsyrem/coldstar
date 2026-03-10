"""
Transaction Mode Selector

Handles the user's explicit choice between public and private
transaction modes. The mode is determined BEFORE signing and
cannot be changed after proof generation.

SECURITY:
- Mode must be explicitly selected, never defaulted
- Mode is stored in the transaction context
- Mode switching after proof creation is forbidden
- The signer must reject ambiguous mode states
"""

import enum
from dataclasses import dataclass
from typing import Optional

from src.zk.types import TransactionMode


class ModeState(enum.Enum):
    """State machine for transaction mode lifecycle.

    Transitions:
        UNSELECTED -> SELECTED -> LOCKED
        (Any state) -> REJECTED (terminal)

    Once LOCKED, the mode cannot be changed without starting a new transaction.
    """
    UNSELECTED = "unselected"     # No mode chosen yet
    SELECTED = "selected"         # User has chosen a mode
    LOCKED = "locked"             # Proofs generated / signing prep done — no changes
    REJECTED = "rejected"         # Mode was rejected (e.g., invalid transition)


@dataclass
class ModeSelection:
    """The result of a mode selection operation."""
    mode: Optional[TransactionMode]
    state: ModeState
    reason: str = ""

    @property
    def is_valid(self) -> bool:
        return self.mode is not None and self.state in (ModeState.SELECTED, ModeState.LOCKED)

    @property
    def is_locked(self) -> bool:
        return self.state == ModeState.LOCKED


class ModeSelector:
    """Transaction mode selector.

    Manages the lifecycle of mode selection for a single transaction.

    Usage:
        selector = ModeSelector()
        selector.select("private")  # User chooses mode
        selector.lock()             # Lock after proof generation
        # selector.select("public") -> raises error (locked)
    """

    def __init__(self):
        self._mode: Optional[TransactionMode] = None
        self._state: ModeState = ModeState.UNSELECTED
        self._reason: str = ""

    @property
    def mode(self) -> Optional[TransactionMode]:
        return self._mode

    @property
    def state(self) -> ModeState:
        return self._state

    @property
    def selection(self) -> ModeSelection:
        return ModeSelection(mode=self._mode, state=self._state, reason=self._reason)

    def select(self, mode_str: str) -> ModeSelection:
        """Select a transaction mode.

        Args:
            mode_str: "public" or "private"

        Returns:
            ModeSelection result

        Raises:
            ValueError if mode is invalid or state transition is forbidden
        """
        if self._state == ModeState.LOCKED:
            raise ValueError(
                "Cannot change mode after proof generation. "
                "Start a new transaction to change modes."
            )

        if self._state == ModeState.REJECTED:
            raise ValueError(
                "Transaction mode was rejected. Start a new transaction."
            )

        mode = TransactionMode.from_str_strict(mode_str)
        if mode is None:
            self._state = ModeState.REJECTED
            self._reason = f"Invalid mode: '{mode_str}'. Must be 'public' or 'private'."
            raise ValueError(self._reason)

        self._mode = mode
        self._state = ModeState.SELECTED
        self._reason = f"Mode set to {mode.value}"

        return self.selection

    def lock(self) -> ModeSelection:
        """Lock the mode — prevents further changes.

        Should be called after proof generation (private) or
        before signing (public).

        Raises:
            ValueError if no mode has been selected
        """
        if self._state == ModeState.UNSELECTED:
            raise ValueError("Cannot lock — no mode has been selected")

        if self._state == ModeState.REJECTED:
            raise ValueError("Cannot lock — mode was rejected")

        self._state = ModeState.LOCKED
        self._reason = f"Mode locked to {self._mode.value}"
        return self.selection

    def reset(self):
        """Reset the selector for a new transaction."""
        self._mode = None
        self._state = ModeState.UNSELECTED
        self._reason = ""

    def require_mode(self, expected: TransactionMode) -> bool:
        """Check that the current mode matches expected.

        Args:
            expected: The expected mode

        Returns:
            True if mode matches

        Raises:
            ValueError if mode doesn't match or isn't selected
        """
        if self._mode is None:
            raise ValueError("No mode selected")
        if self._mode != expected:
            raise ValueError(
                f"Mode mismatch: expected {expected.value}, got {self._mode.value}"
            )
        return True

    def display_status(self) -> str:
        """Get a human-readable status string."""
        if self._state == ModeState.UNSELECTED:
            return "Mode: NOT SELECTED"
        elif self._state == ModeState.SELECTED:
            return f"Mode: {self._mode.value.upper()} (selected, not locked)"
        elif self._state == ModeState.LOCKED:
            return f"Mode: {self._mode.value.upper()} (LOCKED)"
        elif self._state == ModeState.REJECTED:
            return f"Mode: REJECTED ({self._reason})"
        return "Mode: UNKNOWN"
