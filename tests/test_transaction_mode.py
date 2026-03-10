"""
Tests for the transaction mode selector.
"""

import pytest
from src.privacy.mode import ModeSelector, ModeState, ModeSelection
from src.zk.types import TransactionMode


class TestModeSelector:
    def test_initial_state(self):
        sel = ModeSelector()
        assert sel.mode is None
        assert sel.state == ModeState.UNSELECTED

    def test_select_public(self):
        sel = ModeSelector()
        result = sel.select("public")
        assert result.mode == TransactionMode.PUBLIC
        assert result.state == ModeState.SELECTED
        assert result.is_valid is True

    def test_select_private(self):
        sel = ModeSelector()
        result = sel.select("private")
        assert result.mode == TransactionMode.PRIVATE
        assert result.state == ModeState.SELECTED

    def test_lock(self):
        sel = ModeSelector()
        sel.select("private")
        result = sel.lock()
        assert result.state == ModeState.LOCKED
        assert result.is_locked is True

    def test_cannot_change_after_lock(self):
        sel = ModeSelector()
        sel.select("private")
        sel.lock()
        with pytest.raises(ValueError, match="Cannot change mode after proof"):
            sel.select("public")

    def test_cannot_lock_without_selection(self):
        sel = ModeSelector()
        with pytest.raises(ValueError, match="no mode has been selected"):
            sel.lock()

    def test_invalid_mode_rejects(self):
        sel = ModeSelector()
        with pytest.raises(ValueError, match="Invalid mode"):
            sel.select("stealth")
        assert sel.state == ModeState.REJECTED

    def test_cannot_select_after_rejection(self):
        sel = ModeSelector()
        try:
            sel.select("bad")
        except ValueError:
            pass
        with pytest.raises(ValueError, match="rejected"):
            sel.select("public")

    def test_reset(self):
        sel = ModeSelector()
        sel.select("public")
        sel.lock()
        sel.reset()
        assert sel.mode is None
        assert sel.state == ModeState.UNSELECTED

    def test_reselect_before_lock(self):
        sel = ModeSelector()
        sel.select("public")
        sel.select("private")
        assert sel.mode == TransactionMode.PRIVATE

    def test_require_mode_match(self):
        sel = ModeSelector()
        sel.select("public")
        assert sel.require_mode(TransactionMode.PUBLIC) is True

    def test_require_mode_mismatch(self):
        sel = ModeSelector()
        sel.select("public")
        with pytest.raises(ValueError, match="mismatch"):
            sel.require_mode(TransactionMode.PRIVATE)

    def test_require_mode_none(self):
        sel = ModeSelector()
        with pytest.raises(ValueError, match="No mode selected"):
            sel.require_mode(TransactionMode.PUBLIC)

    def test_display_status(self):
        sel = ModeSelector()
        assert "NOT SELECTED" in sel.display_status()
        sel.select("public")
        assert "PUBLIC" in sel.display_status()
        sel.lock()
        assert "LOCKED" in sel.display_status()


class TestModeSelection:
    def test_is_valid_true(self):
        ms = ModeSelection(mode=TransactionMode.PUBLIC, state=ModeState.SELECTED)
        assert ms.is_valid is True

    def test_is_valid_false_unselected(self):
        ms = ModeSelection(mode=None, state=ModeState.UNSELECTED)
        assert ms.is_valid is False

    def test_is_locked(self):
        ms = ModeSelection(mode=TransactionMode.PRIVATE, state=ModeState.LOCKED)
        assert ms.is_locked is True
