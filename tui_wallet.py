#!/usr/bin/env python3
"""
Coldstar TUI Wallet - Live version with real wallet integration
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Button, Input, Label
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from datetime import datetime
from typing import Optional

# Import wallet components
from src.wallet import WalletManager
from src.usb import USBManager
from src.network import SolanaNetwork
from src.transaction import TransactionManager
from src.token_fetcher import TokenFetcher
from src.token_logos import TokenLogoManager
from config import SOLANA_RPC_URL

class LiveStatusBar(Static):
    """Top status bar with live wallet info"""

    wallet_name = reactive("No USB")
    mode = reactive("OFFLINE")
    network_status = reactive("Disconnected")

    def render(self) -> Text:
        text = Text()
        text.append("❄ COLDSTAR", style="bold #38bdf8")
        text.append("  ", style="")
        text.append(f"{self.wallet_name}", style="#7dd3fc")
        text.append("  ", style="")
        if self.mode == "SYNCING...":
            text.append(self.mode, style="bold #f59e0b")
        elif self.mode == "OFFLINE":
            text.append(self.mode, style="bold #ef4444")
        else:
            text.append(self.mode, style="bold #4ade80")
        text.append("  ", style="")
        if "Connected" in self.network_status:
            text.append("● ", style="#4ade80")
            text.append(self.network_status, style="#4ade80")
        else:
            text.append("● ", style="#ef4444")
            text.append(self.network_status, style="#ef4444")
        return text

class LiveInfoBar(Static):
    """Second bar with live sync status and portfolio value"""

    balance = reactive(0.0)
    last_sync = reactive("Never")
    warnings = reactive(0)
    public_key = reactive("")

    def render(self) -> Text:
        text = Text()
        text.append("Wallet: ", style="#64748b")
        if self.public_key:
            text.append(f"{self.public_key[:8]}...{self.public_key[-8:]}", style="bold #38bdf8")
        else:
            text.append("(No wallet loaded)", style="#ef4444")
        text.append("   ", style="")
        text.append(f"{self.balance:.6f} SOL", style="bold #4ade80")
        text.append("   ", style="")
        text.append(f"sync {self.last_sync}", style="#64748b")
        if self.warnings > 0:
            text.append(f"   ⚠ {self.warnings}", style="#f59e0b")
        return text

class LivePortfolioPanel(Static):
    """Portfolio panel with live multi-token balance"""

    can_focus = True  # Allow arrow key focus

    BINDINGS = [
        Binding("up", "select_prev", "Previous token", show=False),
        Binding("down", "select_next", "Next token", show=False),
    ]

    sol_balance = reactive(0.0)
    tokens = reactive([])
    public_key = reactive("")
    selected_index = reactive(0)  # 0 = SOL, 1+ = tokens

    def compose(self) -> ComposeResult:
        yield Static(" PORTFOLIO  ↑↓ select  TAB focus", classes="panel-header")
        yield ScrollableContainer(
            Static("", id="portfolio-content")
        )

    def on_mount(self) -> None:
        """Render initial state on mount"""
        self.refresh_portfolio()

    def action_select_prev(self) -> None:
        """Move selection up"""
        if self.selected_index > 0:
            self.selected_index -= 1

    def action_select_next(self) -> None:
        """Move selection down"""
        max_index = len(self.tokens)  # 0=SOL, 1..N=tokens
        if self.selected_index < max_index:
            self.selected_index += 1

    def watch_sol_balance(self, balance: float) -> None:
        """Update display when SOL balance changes"""
        self.refresh_portfolio()

    def watch_tokens(self, tokens: list) -> None:
        """Update display when tokens change"""
        self.refresh_portfolio()

    def watch_public_key(self, key: str) -> None:
        """Update display when public key changes"""
        self.refresh_portfolio()

    def watch_selected_index(self, index: int) -> None:
        """Update display when selection changes"""
        self.refresh_portfolio()
        # Notify the app about selection change
        self.post_message(self.TokenSelected(index))

    class TokenSelected(Message):
        """Message when a token is selected"""
        def __init__(self, index: int):
            super().__init__()
            self.index = index

    def refresh_portfolio(self) -> None:
        """Refresh the multi-token portfolio display"""
        content = self.query_one("#portfolio-content", Static)
        text = Text()

        # Get logo manager from app
        logo_manager = self.app.logo_manager

        # Highlight colours
        SEL_BG   = "on #1e3a5f"   # selected row background
        SEL_NAME = f"bold white {SEL_BG}"
        SEL_BAL  = f"bold #38bdf8 {SEL_BG}"
        SEL_USD  = f"bold #4ade80 {SEL_BG}"
        SEL_PFX  = f"bold #38bdf8 {SEL_BG}"
        UNS_NAME = "bold #94a3b8"
        UNS_BAL  = "#7dd3fc"
        UNS_USD  = "#4ade80"

        def _usd(symbol: str, balance: float) -> float:
            if symbol in ("USDC", "USDT"): return balance
            if symbol == "RAY":  return balance * 0.17
            if symbol == "BONK": return balance * 0.00001
            if symbol == "JUP":  return balance * 0.65
            return 0.0

        def _bal_str(balance: float) -> str:
            return f"{balance:,.2f}" if balance >= 1000 else f"{balance:.4f}"

        # SOL row (index 0)
        is_sel = self.selected_index == 0
        sol_icon = logo_manager.get_token_icon("SOL")
        sol_value = self.sol_balance * 147.50
        bg = SEL_BG if is_sel else ""
        text.append("\n")
        text.append(f" {'◆' if is_sel else ' '} {sol_icon}{'SOL':<8}", style=SEL_PFX if is_sel else UNS_NAME)
        text.append(f"{self.sol_balance:>12.4f}", style=SEL_BAL if is_sel else UNS_BAL)
        text.append(f"  ${sol_value:>8.2f} ", style=SEL_USD if is_sel else UNS_USD)

        # SPL token rows
        for idx, token in enumerate(self.tokens, start=1):
            symbol  = token.get("symbol", "Unknown")
            balance = token.get("balance", 0)
            is_sel  = self.selected_index == idx
            icon    = logo_manager.get_token_icon(symbol)
            usd_val = _usd(symbol, balance)
            bal_str = _bal_str(balance)

            text.append("\n")
            text.append(f" {'◆' if is_sel else ' '} {icon}{symbol:<8}", style=SEL_PFX if is_sel else UNS_NAME)
            text.append(f"{bal_str:>12}", style=SEL_BAL if is_sel else UNS_BAL)
            if usd_val > 0:
                text.append(f"  ${usd_val:>8.2f} ", style=SEL_USD if is_sel else UNS_USD)
            else:
                text.append(f"  {'—':>9} ", style=f"dim {SEL_BG}" if is_sel else "dim")

        # Total portfolio value
        total_value = sol_value + sum([
            t.get("balance", 0) if t.get("symbol") in ["USDC", "USDT"] else 0
            for t in self.tokens
        ])

        text.append(f"\n\n{'━' * 40}\n", style="bold cyan")
        text.append(f"  TOTAL  ", style="bold white on dark_green")
        text.append(f"  ${total_value:,.2f} USD", style="bold green")

        # ALWAYS show full public key section for copying
        text.append(f"\n\n{'─' * 40}\n", style="dim")
        text.append("Public Key  ", style="cyan bold")
        text.append("[c] copy\n", style="cyan dim")
        if self.public_key:
            text.append(f"{self.public_key[:44]}\n", style="cyan")
            text.append(f"{self.public_key[44:]}", style="cyan")
        else:
            text.append("(No wallet loaded)\n", style="dim red")

        content.update(text)

class TokenDetailsPanel(Static):
    """Top panel - Selected token details"""

    selected_token = reactive(None)
    sol_balance = reactive(0.0)

    def compose(self) -> ComposeResult:
        yield Static(" TOKEN DETAILS", classes="panel-header")
        yield ScrollableContainer(
            Static("", id="token-details-content")
        )

    def watch_selected_token(self, token: dict) -> None:
        """Update when selected token changes"""
        self.refresh_details()

    def watch_sol_balance(self, balance: float) -> None:
        """Update when SOL balance changes"""
        self.refresh_details()

    def refresh_details(self) -> None:
        """Refresh token details display"""
        content = self.query_one("#token-details-content", Static)
        text = Text()

        # Get logo manager from app
        logo_manager = self.app.logo_manager

        if self.selected_token is None:
            # Default: Show SOL details
            sol_icon = logo_manager.get_token_icon("SOL")

            text.append(f"\n{sol_icon}", style="")
            text.append("SOL (Solana)\n", style="bold white")
            text.append("─" * 35 + "\n\n", style="dim")

            text.append("Native Token\n", style="dim")
            text.append(f"Decimals: 9\n", style="dim")
            text.append(f"Balance: {self.sol_balance:.9f} SOL\n", style="cyan")
            text.append(f"Value: ${self.sol_balance * 147.50:.2f} USD\n\n", style="green")

            text.append("Network Info:\n", style="bold dim")
            text.append("• Fast & low-cost transactions\n", style="dim")
            text.append("• Proof of Stake consensus\n", style="dim")
            text.append("• ~400ms block time\n", style="dim")
        else:
            # Show selected token details
            symbol = self.selected_token.get("symbol", "Unknown")
            mint = self.selected_token.get("mint", "")
            balance = self.selected_token.get("balance", 0)
            decimals = self.selected_token.get("decimals", 0)

            # Get real token logo image or empty string (NO FALLBACK)
            icon = logo_manager.get_token_icon(symbol)

            text.append(f"\n{icon}", style="")
            text.append(f"{symbol}\n", style="bold white")
            text.append("─" * 35 + "\n\n", style="dim")

            text.append(f"Mint: {mint[:20]}...\n", style="dim")
            text.append(f"     ...{mint[-20:]}\n", style="dim")
            text.append(f"Decimals: {decimals}\n", style="dim")
            text.append(f"Type: SPL Token\n\n", style="dim")

            if balance >= 1000:
                balance_str = f"{balance:,.2f}"
            else:
                balance_str = f"{balance:.4f}"

            text.append(f"Balance: {balance_str} {symbol}\n", style="cyan")

            # Calculate USD value
            usd_value = 0.0
            if symbol in ["USDC", "USDT"]:
                usd_value = balance
                text.append(f"Value: ${usd_value:,.2f} USD\n", style="green")
                text.append("\n💰 Stablecoin (1:1 USD)\n", style="dim")
            elif symbol == "RAY":
                usd_value = balance * 0.17
                text.append(f"Value: ${usd_value:,.2f} USD\n", style="green")
            elif symbol == "BONK":
                usd_value = balance * 0.00001
                text.append(f"Value: ${usd_value:,.6f} USD\n", style="green")
            elif symbol == "JUP":
                usd_value = balance * 0.65
                text.append(f"Value: ${usd_value:,.2f} USD\n", style="green")

            # Token-specific info
            if symbol == "USDC":
                text.append("\nToken Info:\n", style="bold dim")
                text.append("• Circle USD Coin\n", style="dim")
                text.append("• Verified stablecoin\n", style="dim")
                text.append("• Widely accepted\n", style="dim")

        content.update(text)

class TokenSecurityPanel(Static):
    """Bottom-centre panel - RugCheck security info"""

    selected_token = reactive(None)
    security_data = reactive(None)

    def compose(self) -> ComposeResult:
        yield Static(" TOKEN SECURITY", classes="panel-header")
        yield ScrollableContainer(
            Static("", id="security-content")
        )

    def watch_selected_token(self, token: dict) -> None:
        """Fetch security data when token changes"""
        if token and token.get("mint"):
            mint = token["mint"]
            # Reset to loading state
            self.security_data = None
            # Fetch in background
            self.app.run_worker(
                lambda: self._fetch_security(mint),
                thread=True
            )
        else:
            self.security_data = None
            self.refresh_security()

    def watch_security_data(self, data: dict) -> None:
        """Update display when security data arrives"""
        self.refresh_security()

    def _fetch_security(self, mint: str) -> None:
        """Background worker: fetch RugCheck data"""
        if "devnet" in SOLANA_RPC_URL or "testnet" in SOLANA_RPC_URL:
            self.app.call_from_thread(setattr, self, "security_data", {"error": "non_mainnet"})
            return
        try:
            url = f"https://premium.rugcheck.xyz/v1/tokens/{mint}/report"
            headers = {"X-API-KEY": "f1de9137-eb1d-4341-9da7-b6920b4839c4"}
            response = None
            try:
                import httpx
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, headers=headers)
            except Exception:
                try:
                    import requests
                    response = requests.get(url, headers=headers, timeout=10)
                except Exception as e:
                    self.app.call_from_thread(setattr, self, "security_data", {"error": f"http_client:{str(e)[:30]}"})
                    return

            if response is None:
                self.app.call_from_thread(setattr, self, "security_data", {"error": "no_response"})
                return

            if response.status_code == 200:
                self.app.call_from_thread(setattr, self, "security_data", response.json())
            elif response.status_code in (401, 403):
                self.app.call_from_thread(setattr, self, "security_data", {"error": "auth"})
            elif response.status_code == 429:
                self.app.call_from_thread(setattr, self, "security_data", {"error": "rate_limited"})
            elif response.status_code == 400:
                # 400 = invalid/unknown token (likely not indexed)
                self.app.call_from_thread(setattr, self, "security_data", {"error": "unknown_token"})
            else:
                self.app.call_from_thread(setattr, self, "security_data", {"error": f"API error {response.status_code}"})
        except Exception as e:
            self.app.call_from_thread(setattr, self, "security_data", {"error": f"Check failed: {str(e)[:30]}"})

    def refresh_security(self) -> None:
        """Refresh security display"""
        content = self.query_one("#security-content", Static)
        text = Text()

        if not self.selected_token:
            text.append("\nSelect an SPL token to view security info\n", style="dim")
        elif not self.security_data:
            text.append("\nLoading security check...\n", style="#f59e0b")
        elif "error" in self.security_data:
            error = self.security_data['error']
            if error == "non_mainnet":
                text.append("\nℹ Info\n", style="bold #38bdf8")
                text.append("─" * 35 + "\n\n", style="dim")
                text.append("Security checks are only available\n", style="dim")
                text.append("on mainnet.\n\n", style="dim")
            elif error == "unknown_token":
                text.append("\nℹ Info\n", style="bold #38bdf8")
                text.append("─" * 35 + "\n\n", style="dim")
                text.append("Token not indexed yet by RugCheck.\n", style="dim")
                text.append("Try again later.\n\n", style="dim")
            elif error == "auth":
                text.append("\n⚠ RugCheck API Key\n", style="bold #f59e0b")
                text.append("─" * 35 + "\n\n", style="dim")
                text.append("API key invalid or expired.\n", style="dim")
                text.append("Update the RugCheck key.\n\n", style="dim")
            elif error == "rate_limited":
                text.append("\n⏳ Rate Limited\n", style="bold #f59e0b")
                text.append("─" * 35 + "\n\n", style="dim")
                text.append("Too many requests. Try again.\n\n", style="dim")
            elif error.startswith("http_client"):
                text.append("\n⚠ HTTP Client Error\n", style="bold #f59e0b")
                text.append("─" * 35 + "\n\n", style="dim")
                text.append("Failed to call RugCheck API.\n", style="dim")
                text.append("Install httpx or requests.\n\n", style="dim")
            else:
                text.append("\n⚠ Security Check Failed\n", style="bold #f59e0b")
                text.append("─" * 35 + "\n\n", style="dim")
                text.append(f"Error: {error}\n", style="dim")
                text.append("Try again later.\n\n", style="dim")
        else:
            # Display RugCheck results
            data = self.security_data
            symbol = self.selected_token.get("symbol", "TOKEN")

            text.append(f"\n{symbol} Security Report\n", style="bold white")
            text.append("─" * 35 + "\n\n", style="dim")

            # Safety Score (0-1 normalized)
            score = data.get("score_normalised", 0)
            score_pct = int(score * 100)

            if score >= 0.8:
                text.append("Safety Score: ", style="dim")
                text.append(f"{score_pct}% ", style="bold #4ade80")
                text.append("✓ GOOD\n", style="#4ade80")
            elif score >= 0.5:
                text.append("Safety Score: ", style="dim")
                text.append(f"{score_pct}% ", style="bold #f59e0b")
                text.append("⚠ WARNING\n", style="#f59e0b")
            else:
                text.append("Safety Score: ", style="dim")
                text.append(f"{score_pct}% ", style="bold #ef4444")
                text.append("⚠ DANGER\n", style="#ef4444")

            text.append("\n", style="")

            # Rugged status
            if data.get("rugged"):
                text.append("⛔ RUGGED TOKEN DETECTED\n\n", style="bold #ef4444")

            # Key metrics
            text.append("Token Info:\n", style="bold dim")

            token_type = data.get("tokenType") or "Unknown"
            if token_type:
                text.append(f"• Type: {token_type}\n", style="dim")

            holders = data.get("totalHolders", 0)
            if holders > 0:
                text.append(f"• Holders: {holders:,}\n", style="dim")

            liq = data.get("totalStableLiquidity", 0)
            if liq > 0:
                text.append(f"• Liquidity: ${liq:,.0f}\n", style="dim")

            # Risks
            risks = data.get("risks")
            if risks:
                text.append("\n⚠ Risks Detected:\n", style="bold #f59e0b")
                risk_list = []
                for risk_item in risks[:5]:
                    if isinstance(risk_item, dict):
                        risk_list.append(risk_item.get("name", str(risk_item)))
                    else:
                        risk_list.append(str(risk_item))
                for risk_name in risk_list:
                    text.append(f"• {risk_name}\n", style="#f59e0b")

        content.update(text)

class TransactionHistoryPanel(Static):
    """Bottom panel - Transaction history"""

    can_focus = True

    BINDINGS = [
        Binding("up", "select_prev", "Previous tx", show=False),
        Binding("down", "select_next", "Next tx", show=False),
    ]

    transactions = reactive([])
    page_size = reactive(5)  # Start with 5, load more on demand
    selected_index = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static(" TRANSACTIONS", classes="panel-header")
        yield ScrollableContainer(
            Static("", id="tx-history-content"),
            Button("Load more...", id="btn-load-more", variant="default"),
        )
        yield Static("", id="tx-detail")

    def on_mount(self) -> None:
        self.query_one("#btn-load-more").display = False

    def watch_transactions(self, txs: list) -> None:
        """Update when transactions change"""
        self.page_size = 5  # Reset to first page on new data
        if self.selected_index >= len(txs):
            self.selected_index = max(0, len(txs) - 1)
        self.refresh_history()

    def watch_page_size(self, size: int) -> None:
        self.refresh_history()

    def watch_selected_index(self, index: int) -> None:
        self.refresh_history()

    def action_select_prev(self) -> None:
        if self.selected_index > 0:
            self.selected_index -= 1

    def action_select_next(self) -> None:
        if self.selected_index < max(0, len(self.transactions) - 1):
            self.selected_index += 1
            if self.selected_index >= self.page_size and self.page_size < len(self.transactions):
                self.page_size += 5

    def get_selected_signature(self) -> Optional[str]:
        if not self.transactions:
            return None
        return self.transactions[self.selected_index].get("signature")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-load-more":
            self.page_size += 5
            self.post_message(self.LoadMore())

    class LoadMore(Message):
        """Request more transactions from the app"""
        pass

    def refresh_history(self) -> None:
        """Refresh transaction history"""
        content = self.query_one("#tx-history-content", Static)
        btn = self.query_one("#btn-load-more")
        detail = self.query_one("#tx-detail", Static)
        text = Text()

        if not self.transactions:
            text.append("\nNo transactions yet\n", style="dim")
            btn.display = False
            detail.update("[dim]Select a transaction to view details[/dim]")
        else:
            visible = self.transactions[:self.page_size]
            has_more = len(self.transactions) > self.page_size
            for idx, tx in enumerate(visible):
                signature = tx.get("signature", "Unknown")
                err = tx.get("err")
                status = "✓" if err is None else "✗"
                status_color = "green" if err is None else "red"
                is_sel = idx == self.selected_index

                block_time = tx.get("blockTime")
                if block_time:
                    import datetime as dt_mod
                    dt = dt_mod.datetime.fromtimestamp(block_time)
                    time_str = dt.strftime("%m/%d %H:%M")
                else:
                    time_str = "Pending  "

                sig_short = f"{signature[:6]}...{signature[-6:]}"

                # Direction arrow + amount
                direction = tx.get("direction")
                sol_delta = tx.get("sol_delta")

                if direction == "sent" and sol_delta is not None:
                    dir_str = "↑ SENT    "
                    dir_color = "red"
                    amt_str = f"-{abs(sol_delta):.6f} SOL"
                    amt_color = "red"
                elif direction == "received" and sol_delta is not None:
                    dir_str = "↓ RECV    "
                    dir_color = "green"
                    amt_str = f"+{abs(sol_delta):.6f} SOL"
                    amt_color = "green"
                else:
                    dir_str = "  ------  "
                    dir_color = "dim"
                    amt_str = ""
                    amt_color = "dim"

                row_style = "on #1e3a5f" if is_sel else ""
                text.append(f"\n{status} ", style=f"{status_color} {row_style}".strip())
                text.append(f"{time_str}  ", style="dim")
                text.append(f"{dir_str}", style=f"{dir_color} {row_style}".strip())
                if amt_str:
                    text.append(f"{amt_str:<18}", style=f"{amt_color} {row_style}".strip())
                text.append(sig_short, style=f"cyan {row_style}".strip())
                if err:
                    text.append("  FAILED", style=f"bold red {row_style}".strip())

            btn.display = has_more
            if has_more:
                remaining = len(self.transactions) - self.page_size
                btn.label = f"Load {min(remaining, 5)} more  ({remaining} remaining)"

        content.update(text)

        if self.transactions:
            tx = self.transactions[self.selected_index]
            signature = tx.get("signature", "")
            slot = tx.get("slot", "N/A")
            err = tx.get("err")
            block_time = tx.get("blockTime")
            time_str = datetime.fromtimestamp(block_time).strftime("%Y-%m-%d %H:%M:%S") if block_time else "Pending"
            sol_delta = tx.get("sol_delta")
            fee_sol = tx.get("fee_sol")
            delta_str = f"{sol_delta:+.6f} SOL" if isinstance(sol_delta, (int, float)) else "—"
            fee_str = f"{fee_sol:.6f} SOL" if isinstance(fee_sol, (int, float)) else "—"
            status = "✓ Success" if err is None else "✗ Failed"
            link = ""
            try:
                link = self.app._tx_explorer_link(signature)
            except Exception:
                link = ""
            detail.update(
                f"[bold]Selected:[/bold] {signature[:10]}...{signature[-10:]}\n"
                f"Status: {status}\n"
                f"Slot: {slot}  Time: {time_str}\n"
                f"Amount: {delta_str}  Fee: {fee_str}\n"
                f"Explorer: {link}\n"
                f"[dim]Press x to copy explorer link[/dim]"
            )

class LiveSendPanel(Static):
    """Send panel with live wallet connection"""

    current_balance = reactive(0.0)
    _confirming = False  # True when showing password confirm step

    def compose(self) -> ComposeResult:
        yield Static(" SEND TOKENS", classes="panel-header")
        yield Container(
            # Review box at the top so it's always visible
            Static("Fill in address and amount below", id="review-box"),
            Static("", id="fee-info"),
            Static("", id="balance-info"),
            Label("To Address:"),
            Input(placeholder="Enter recipient address", id="to-address"),
            Label("Amount (SOL):"),
            Horizontal(
                Input(placeholder="0.0", id="amount-input"),
                Button("25%", id="btn-25"),
                Button("50%", id="btn-50"),
                Button("75%", id="btn-75"),
                Button("MAX", id="btn-max"),
            ),
            # Action buttons below inputs
            Horizontal(
                Button("Send", variant="success", id="btn-send"),
                Button("Clear", id="btn-cancel"),
                id="send-buttons"
            ),
            # Confirmation step - hidden until Send is clicked
            Container(
                Static("", id="confirm-summary"),
                Label("Wallet Password:"),
                Input(placeholder="Enter password to sign", id="wallet-password", password=True),
                Horizontal(
                    Button("Confirm Send", variant="error", id="btn-confirm"),
                    Button("Go Back", id="btn-back"),
                ),
                id="confirm-container"
            ),
            id="send-container"
        )

    def on_mount(self) -> None:
        """Hide confirm section on mount"""
        self.query_one("#confirm-container").display = False
        self.update_balance_info()

    def watch_current_balance(self, balance: float) -> None:
        self.update_balance_info()

    def update_balance_info(self) -> None:
        balance_info = self.query_one("#balance-info", Static)
        balance_info.update(f"Available: {self.current_balance:.9f} SOL")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-25":
            self.set_amount(self.current_balance * 0.25)
        elif event.button.id == "btn-50":
            self.set_amount(self.current_balance * 0.50)
        elif event.button.id == "btn-75":
            self.set_amount(self.current_balance * 0.75)
        elif event.button.id == "btn-max":
            self.set_amount(max(0, self.current_balance - 0.000005))
        elif event.button.id == "btn-send":
            self._show_confirm_step()
        elif event.button.id == "btn-cancel":
            self.clear_form()
        elif event.button.id == "btn-confirm":
            self.post_message(self.SendRequested())
        elif event.button.id == "btn-back":
            self._hide_confirm_step()

    def _show_confirm_step(self) -> None:
        """Validate inputs then show password + confirm button"""
        review = self.query_one("#review-box", Static)
        to = self.query_one("#to-address", Input).value.strip()
        amount_str = self.query_one("#amount-input", Input).value.strip()

        if not to or not amount_str:
            review.update("[red]Fill in address and amount first[/red]")
            return
        # Validate address format
        if not self.app.wallet_manager.validate_address(to):
            review.update("[red]Invalid recipient address[/red]")
            return
        try:
            amount = float(amount_str)
        except ValueError:
            review.update("[red]Invalid amount[/red]")
            return
        if amount <= 0:
            review.update("[red]Amount must be greater than 0[/red]")
            return
        # Fee-aware balance check
        fee = 0.000005
        if amount + fee > self.current_balance:
            review.update("[red]Insufficient balance (amount + fee)[/red]")
            return

        # Show the confirmation section
        to_short = f"{to[:6]}...{to[-6:]}" if len(to) > 12 else to
        summary = self.query_one("#confirm-summary", Static)
        summary.update(
            f"[bold yellow]Confirm Transaction[/bold yellow]\n"
            f"[dim]──────────────────────[/dim]\n"
            f"Send  [bold cyan]{amount:.6f} SOL[/bold cyan]\n"
            f"To    [cyan]{to_short}[/cyan]\n"
            f"Fee   [dim]{fee:.6f} SOL[/dim]"
        )
        self.query_one("#confirm-container").display = True
        self.query_one("#wallet-password", Input).focus()
        self._confirming = True

    def _hide_confirm_step(self) -> None:
        """Go back to the input form"""
        self.query_one("#confirm-container").display = False
        self.query_one("#wallet-password", Input).value = ""
        self._confirming = False

    def set_amount(self, amount: float) -> None:
        self.query_one("#amount-input", Input).value = f"{amount:.9f}"
        self.update_review()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("to-address", "amount-input"):
            self.update_review()

    def update_review(self) -> None:
        review = self.query_one("#review-box", Static)
        fee_info = self.query_one("#fee-info", Static)
        try:
            to = self.query_one("#to-address", Input).value.strip()
            amount_str = self.query_one("#amount-input", Input).value.strip()
            amount = float(amount_str) if amount_str else 0.0
            fee = 0.000005
            fee_info.update(f"Fee: ~{fee:.6f} SOL")
            if to and amount > 0:
                to_short = f"{to[:6]}...{to[-6:]}" if len(to) > 12 else to
                review.update(
                    f"[bold cyan]{amount:.6f} SOL[/bold cyan]"
                    f"  [dim]→[/dim]  [cyan]{to_short}[/cyan]"
                )
            else:
                review.update("[dim]Fill in address and amount below[/dim]")
        except (ValueError, TypeError):
            review.update("[red]Invalid amount[/red]")

    def clear_form(self) -> None:
        self._hide_confirm_step()
        self.query_one("#to-address", Input).value = ""
        self.query_one("#amount-input", Input).value = ""
        self.query_one("#review-box", Static).update("[dim]Fill in address and amount below[/dim]")
        self.query_one("#fee-info", Static).update("")

    class SendRequested(Message):
        """User confirmed send - app handles signing + broadcast"""
        pass

class LiveBottomBar(Static):
    """Bottom shortcuts bar"""

    def render(self) -> Text:
        text = Text()
        text.append("TAB", style="bold #38bdf8")
        text.append(" Navigate  ", style="#64748b")
        text.append("↑↓", style="bold #f59e0b")
        text.append(" Select  ", style="#64748b")
        text.append("r", style="bold #4ade80")
        text.append(" Refresh  ", style="#64748b")
        text.append("c", style="bold #a78bfa")
        text.append(" Copy address  ", style="#64748b")
        text.append("x", style="bold #22c55e")
        text.append(" Copy tx link  ", style="#64748b")
        text.append("u", style="bold #f59e0b")
        text.append(" Unmount  ", style="#64748b")
        text.append("q", style="bold #ef4444")
        text.append(" Quit", style="#64748b")
        return text

class ColdstarLiveWallet(App):
    """Live Coldstar Wallet TUI"""

    CSS = """
    /* ── COLDSTAR THEME ── navy background, ice-blue accents, white text ── */

    Screen {
        background: #0a0e1a;
    }

    /* Top/bottom bars: slightly lighter navy strip */
    LiveStatusBar, LiveInfoBar, LiveBottomBar {
        dock: top;
        height: 1;
        background: #111827;
        color: #e2e8f0;
        padding: 0 1;
    }

    LiveBottomBar {
        dock: bottom;
    }

    /* Panel containers */
    LivePortfolioPanel, LiveSendPanel {
        width: 1fr;
        border: solid #1e3a5f;
        background: #0d1526;
        padding: 0;
        margin: 0 1;
    }

    #left-column, #centre-column, #right-column {
        width: 1fr;
        height: 100%;
        margin: 0 1;
    }

    LivePortfolioPanel {
        height: 1fr;
    }

    TokenDetailsPanel, TokenSecurityPanel {
        height: 1fr;
        border: solid #1e3a5f;
        background: #0d1526;
        padding: 0;
    }

    TransactionHistoryPanel {
        height: 1fr;
        border: solid #1e3a5f;
        background: #0d1526;
        padding: 0;
        margin-top: 1;
    }

    LiveSendPanel {
        height: 1fr;
    }

    DevicePanel {
        height: 5;
        border: solid #1e3a5f;
        background: #0d1526;
        padding: 0;
        margin: 0 1;
    }

    NetworkPanel {
        height: 7;
        border: solid #1e3a5f;
        background: #0d1526;
        padding: 0;
        margin: 0 1;
    }

    #network-container {
        padding: 1;
    }

    #airdrop-status {
        margin: 1 0 0 0;
    }

    #device-list, #device-hint {
        padding: 0 1;
    }

    ConfirmUnmountScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }

    #confirm-container {
        width: 50;
        border: solid #f59e0b;
        background: #0d1526;
        padding: 1 2;
    }

    #confirm-text {
        margin-bottom: 1;
    }

    TokenSecurityPanel {
        margin-top: 1;
    }

    /* Focus: bright ice-blue border, subtle glow */
    LivePortfolioPanel:focus {
        border: heavy #38bdf8;
        background: #0f1f35;
    }

    LivePortfolioPanel:focus-within {
        border: heavy #38bdf8;
        background: #0f1f35;
    }

    LiveSendPanel:focus-within {
        border: heavy #38bdf8;
        background: #0f1f35;
    }

    TokenDetailsPanel:focus-within {
        border: heavy #38bdf8;
        background: #0f1f35;
    }

    TransactionHistoryPanel:focus-within {
        border: heavy #38bdf8;
        background: #0f1f35;
    }

    TokenSecurityPanel:focus-within {
        border: heavy #38bdf8;
        background: #0f1f35;
    }

    /* Panel header bars — styled title strip */
    .panel-header {
        background: #1e3a5f;
        color: #7dd3fc;
        text-style: bold;
        padding: 0 1;
        height: 1;
        dock: top;
    }

    /* Scrollable inner content gets padding */
    ScrollableContainer {
        padding: 0 1;
    }

    ScrollableContainer:focus-within {
        border: none;
    }

    #send-container {
        height: 1fr;
        padding: 0;
        align: left top;
    }

    #review-box, #fee-info, #balance-info {
        height: 1;
        margin-bottom: 0;
    }

    #send-buttons {
        margin: 0 0 0 0;
    }

    /* Labels inside send form */
    Label {
        color: #7dd3fc;
        text-style: bold;
        margin-bottom: 0;
    }

    Input {
        margin-bottom: 0;
        border: solid #1e3a5f;
        background: #0a0e1a;
        color: #e2e8f0;
    }

    Input:focus {
        border: solid #38bdf8;
        background: #0f1f35;
        color: #ffffff;
    }

    Button {
        margin-right: 1;
        border: solid #1e3a5f;
        background: #111827;
        color: #7dd3fc;
    }

    Button:hover {
        background: #1e3a5f;
        border: solid #38bdf8;
        color: #ffffff;
    }

    Button:focus {
        background: #38bdf8;
        border: solid #38bdf8;
        color: #0a0e1a;
        text-style: bold;
    }

    #balance-info, #fee-info {
        color: #64748b;
        margin: 0;
    }

    #review-box {
        border: solid #1e3a5f;
        background: #0f1f35;
        padding: 0 1;
        margin: 0;
        color: #e2e8f0;
    }

    #confirm-container {
        border: solid #f59e0b;
        background: #1a1200;
        padding: 1;
        margin-top: 0;
    }

    #confirm-summary {
        margin-bottom: 1;
        color: #e2e8f0;
    }

    #send-buttons {
        margin: 0;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "copy_address", "Copy Address"),
        Binding("x", "copy_tx_link", "Copy Tx Link"),
        Binding("u", "unmount", "Unmount Wallet"),
    ]

    def __init__(self):
        super().__init__()
        self.wallet_manager = WalletManager()
        self.usb_manager = USBManager()
        self.network = SolanaNetwork()
        self.transaction_manager = TransactionManager()
        self.token_fetcher = TokenFetcher()
        self.logo_manager = TokenLogoManager()

        self.current_public_key = None
        self.current_balance = 0.0
        self.current_tokens = []
        self.did_unmount = False
        self.detected_devices = []
        self.selected_device_index = None
        self._last_mount_attempt = 0.0

        # Preload common token logos in background
        self.logo_manager.preload_common_tokens()

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield LiveStatusBar()
        yield LiveInfoBar()
        yield Horizontal(
            Vertical(
                LivePortfolioPanel(),
                TransactionHistoryPanel(),
                id="left-column"
            ),
            Vertical(
                TokenDetailsPanel(),
                TokenSecurityPanel(),
                id="centre-column"
            ),
            Vertical(
                DevicePanel(),
                NetworkPanel(),
                LiveSendPanel(),
                id="right-column"
            )
        )
        yield LiveBottomBar()

    def on_mount(self) -> None:
        """Initialize wallet connection on startup"""
        self.set_interval(15.0, self.refresh_data)  # Auto-refresh every 15s
        self.refresh_data()

    def refresh_data(self) -> None:
        """Kick off a background worker to fetch data without blocking UI"""
        # Show SYNCING in status bar immediately
        try:
            self.query_one(LiveStatusBar).mode = "SYNCING..."
        except Exception:
            pass
        self.run_worker(self._fetch_wallet_data, exclusive=True, thread=True)

    def _fetch_wallet_data(self) -> None:
        """Background worker - all RPC calls happen here, UI updates via call_from_thread"""
        # Check network
        connected = self.network.is_connected()
        self.call_from_thread(self._update_network_status, connected)
        if connected:
            info = self.network.get_network_info()
            self.call_from_thread(self._update_network_info, info)

        # Detect USB
        devices = self.usb_manager.detect_usb_devices()
        self.call_from_thread(self._update_devices, devices)
        if not devices:
            self.call_from_thread(self._set_mode, "OFFLINE")
            return

        device = None
        if len(devices) == 1:
            device = devices[0]
            self.selected_device_index = 0
        else:
            if self.selected_device_index is None or self.selected_device_index >= len(devices):
                self.call_from_thread(self._set_mode, "SELECT USB")
                return
            device = devices[self.selected_device_index]

        if device is None:
            self.call_from_thread(self._set_mode, "SELECT USB")
            return

        # Sync USB manager state
        self.usb_manager.detected_devices = devices
        if self.selected_device_index is not None:
            self.usb_manager.select_device(self.selected_device_index)

        mount_point = device.get('mountpoint')
        wallet_label = device.get('model', 'COLDSTAR').strip() or 'COLDSTAR'

        if mount_point:
            self.usb_manager.mount_point = mount_point
        else:
            # Attempt to mount if not already mounted (rate-limited)
            import time
            if time.time() - self._last_mount_attempt > 5:
                self._last_mount_attempt = time.time()
                mount_point = self.usb_manager.mount_device(device.get("device"))
                if mount_point:
                    self.usb_manager.mount_point = mount_point

        self.call_from_thread(self._update_status_bar, wallet_label)

        if not self.usb_manager.mount_point:
            return

        pubkey_path = Path(self.usb_manager.mount_point) / "wallet" / "pubkey.txt"
        if not pubkey_path.exists():
            return

        pubkey = pubkey_path.read_text().strip()
        self.current_public_key = pubkey
        self.call_from_thread(self._update_pubkey, pubkey)

        if not connected:
            return

        # Fetch balance
        balance = self.network.get_balance(pubkey)
        if balance is None:
            return
        self.current_balance = balance
        self.call_from_thread(self._update_balance, balance)

        # Fetch tokens
        tokens = self.token_fetcher.get_all_token_balances(pubkey)
        self.current_tokens = tokens
        self.call_from_thread(self._update_tokens, tokens)

        # Fetch tx history + enrich with amounts
        txs = self.network.get_transaction_history(pubkey, 10)
        if txs:
            enriched = self._enrich_transactions(txs, pubkey)
            self.call_from_thread(self._update_txs, enriched)

    def _enrich_transactions(self, txs: list, pubkey: str) -> list:
        """Fetch transaction details to add SOL delta to each tx entry"""
        enriched = []
        for tx in txs:
            entry = dict(tx)  # copy base fields (signature, blockTime, err, etc.)
            try:
                detail = self.network.get_transaction_details(tx["signature"])
                if detail:
                    meta = detail.get("meta", {})
                    msg = detail.get("transaction", {}).get("message", {})
                    account_keys = [a.get("pubkey", "") for a in msg.get("accountKeys", [])]
                    pre = meta.get("preBalances", [])
                    post = meta.get("postBalances", [])
                    fee = meta.get("fee", 0)

                    # Find our wallet's index in the account list
                    if pubkey in account_keys:
                        idx = account_keys.index(pubkey)
                        if idx < len(pre) and idx < len(post):
                            delta_lamports = post[idx] - pre[idx]
                            # If we're the fee payer (idx==0), add fee back to get true send amount
                            if idx == 0 and delta_lamports < 0:
                                send_amount = -(delta_lamports + fee) / 1_000_000_000
                                entry["sol_delta"] = -send_amount  # negative = sent
                                entry["direction"] = "sent"
                            elif delta_lamports > 0:
                                recv_amount = delta_lamports / 1_000_000_000
                                entry["sol_delta"] = recv_amount
                                entry["direction"] = "received"
                            else:
                                entry["sol_delta"] = delta_lamports / 1_000_000_000
                                entry["direction"] = "other"
                    entry["fee_sol"] = fee / 1_000_000_000
            except Exception:
                pass  # If detail fetch fails, show tx without amount
            enriched.append(entry)
        return enriched

    def _update_network_status(self, connected: bool) -> None:
        status_bar = self.query_one(LiveStatusBar)
        status_bar.network_status = "Connected" if connected else "Disconnected"

    def _update_network_info(self, info: dict) -> None:
        panel = self.query_one(NetworkPanel)
        status = "Connected" if self.network.is_connected() else "Disconnected"
        net_info = panel.query_one("#network-info", Static)
        extra = panel.query_one("#network-extra", Static)
        net_info.update(f"RPC: {SOLANA_RPC_URL}\nStatus: {status}")

        if info and "error" not in info:
            extra.update(
                f"Version: {info.get('version', 'Unknown')}\n"
                f"Slot: {info.get('slot', 'Unknown')}\n"
                f"Epoch: {info.get('epoch', 'Unknown')}"
            )
        else:
            extra.update("[dim]Network details unavailable[/dim]")

    def request_airdrop(self, amount: float) -> None:
        """Request a Devnet airdrop in a background worker"""
        self.run_worker(lambda: self._do_airdrop(amount), thread=True)

    def _do_airdrop(self, amount: float) -> None:
        panel = self.query_one(NetworkPanel)
        status = panel.query_one("#airdrop-status", Static)
        if "devnet" not in SOLANA_RPC_URL:
            self.call_from_thread(status.update, "[red]Airdrops only available on Devnet[/red]")
            return
        if not self.current_public_key:
            self.call_from_thread(status.update, "[red]No wallet loaded[/red]")
            return

        signature = self.network.request_airdrop(self.current_public_key, amount)
        if not signature:
            self.call_from_thread(status.update, "[red]Airdrop request failed[/red]")
            return

        self.call_from_thread(status.update, "[yellow]Waiting for confirmation...[/yellow]")
        if self.network.confirm_transaction(signature):
            self.call_from_thread(status.update, "[green]Airdrop confirmed![/green]")
            # Refresh balances after successful airdrop
            import time
            time.sleep(2)
            self.call_from_thread(self.refresh_data)
        else:
            self.call_from_thread(status.update, "[yellow]Airdrop pending confirmation[/yellow]")

    def _update_status_bar(self, label: str) -> None:
        status_bar = self.query_one(LiveStatusBar)
        status_bar.wallet_name = label
        status_bar.mode = "READY"

    def _set_mode(self, mode: str) -> None:
        self.query_one(LiveStatusBar).mode = mode

    def _update_devices(self, devices: list) -> None:
        self.detected_devices = devices or []
        panel = self.query_one(DevicePanel)
        panel.devices = self.detected_devices
        panel.selected_index = self.selected_device_index

    def on_device_panel_device_selected(self, message) -> None:
        self.selected_device_index = message.index
        self.refresh_data()

    def _update_pubkey(self, pubkey: str) -> None:
        self.query_one(LiveInfoBar).public_key = pubkey
        self.query_one(LivePortfolioPanel).public_key = pubkey

    def _update_balance(self, balance: float) -> None:
        from datetime import datetime
        info_bar = self.query_one(LiveInfoBar)
        info_bar.balance = balance
        info_bar.last_sync = datetime.now().strftime("%H:%M:%S")
        self.query_one(LivePortfolioPanel).sol_balance = balance
        self.query_one(LiveSendPanel).current_balance = balance
        self.query_one(TokenDetailsPanel).sol_balance = balance

    def _update_tokens(self, tokens: list) -> None:
        self.query_one(LivePortfolioPanel).tokens = tokens
        # Sync panels to current selection after token refresh
        self._apply_token_selection(self.query_one(LivePortfolioPanel).selected_index)

    def _apply_token_selection(self, index: int) -> None:
        """Apply current token selection to detail/security panels"""
        token_details = self.query_one(TokenDetailsPanel)
        token_security = self.query_one(TokenSecurityPanel)

        if index <= 0:
            # SOL selected - no security check for native token
            token_details.selected_token = None
            token_details.sol_balance = self.current_balance
            token_security.selected_token = None
            return

        if not self.current_tokens:
            token_details.selected_token = None
            token_security.selected_token = None
            return

        if index - 1 >= len(self.current_tokens):
            index = 1  # fallback to first token if selection is out of range

        selected = self.current_tokens[index - 1]
        token_details.selected_token = selected
        token_security.selected_token = selected

    def _update_txs(self, txs: list) -> None:
        self.query_one(TransactionHistoryPanel).transactions = txs

    def on_transaction_history_panel_load_more(self, message: TransactionHistoryPanel.LoadMore) -> None:
        """Fetch next page of transactions from RPC"""
        if not self.current_public_key:
            return
        panel = self.query_one(TransactionHistoryPanel)
        current_txs = panel.transactions
        # Use last signature as cursor for RPC pagination
        if not current_txs:
            return
        last_sig = current_txs[-1].get("signature")
        self.run_worker(
            lambda: self._fetch_more_txs(last_sig, current_txs),
            thread=True
        )

    def on_live_portfolio_panel_token_selected(self, message: LivePortfolioPanel.TokenSelected) -> None:
        """Handle token selection - update details and security panels"""
        self._apply_token_selection(message.index)

    def _fetch_more_txs(self, before_sig: str, existing_txs: list) -> None:
        """Background worker: fetch next 10 txs before the cursor signature"""
        try:
            result = self.network._make_rpc_request(
                "getSignaturesForAddress",
                [self.current_public_key, {"limit": 10, "before": before_sig}]
            )
            new_txs = result.get("result", [])
            if new_txs:
                enriched = self._enrich_transactions(new_txs, self.current_public_key)
                combined = existing_txs + enriched
                self.call_from_thread(self._update_txs, combined)
        except Exception:
            pass

    def on_live_send_panel_send_requested(self, message: LiveSendPanel.SendRequested) -> None:
        """Handle confirmed send - validate then broadcast"""
        send_panel = self.query_one(LiveSendPanel)
        to_addr = send_panel.query_one("#to-address", Input).value.strip()
        amount_str = send_panel.query_one("#amount-input", Input).value.strip()
        password = send_panel.query_one("#wallet-password", Input).value
        review = send_panel.query_one("#review-box", Static)

        if not password:
            send_panel.query_one("#confirm-summary", Static).update(
                "[red]Enter your wallet password above[/red]"
            )
            return
        if not self.wallet_manager.validate_address(to_addr):
            review.update("[red]Error: Invalid recipient address[/red]")
            return
        try:
            amount = float(amount_str)
        except ValueError:
            review.update("[red]Error: Invalid amount[/red]")
            return
        fee = 0.000005
        if amount + fee > self.current_balance:
            review.update("[red]Error: Insufficient balance (amount + fee)[/red]")
            return
        if not self.usb_manager.mount_point:
            review.update("[red]Error: No wallet mounted[/red]")
            return
        if not self.current_public_key:
            review.update("[red]Error: No wallet public key found[/red]")
            return

        # Hide confirm section, show status in review box
        send_panel._hide_confirm_step()
        review.update("[yellow]Sending...[/yellow]")
        self.run_worker(
            lambda: self._do_send(to_addr, amount, password, review),
            thread=True
        )

    def _do_send(self, to_addr: str, amount: float, password: str, review: Static) -> None:
        """Background worker: create, sign, and broadcast a SOL transfer"""
        import base64

        try:
            keypair_path = Path(self.usb_manager.mount_point) / "wallet" / "keypair.json"

            # Step 1: Get latest blockhash
            self.call_from_thread(review.update, "Fetching blockhash...")
            blockhash_result = self.network.get_latest_blockhash()
            if not blockhash_result:
                self.call_from_thread(review.update, "[red]Error: Could not get blockhash[/red]")
                return
            blockhash, _ = blockhash_result

            # Step 2: Create unsigned transaction
            self.call_from_thread(review.update, "Building transaction...")
            unsigned_tx = self.transaction_manager.create_transfer_transaction(
                self.current_public_key,
                to_addr,
                amount,
                blockhash
            )
            if not unsigned_tx:
                self.call_from_thread(review.update, "[red]Error: Could not build transaction[/red]")
                return

            # Step 3: Load encrypted container from USB (no key in Python memory)
            self.call_from_thread(review.update, "Loading wallet container...")
            encrypted_container = self.wallet_manager.load_encrypted_container(
                str(keypair_path),
                password
            )
            if not encrypted_container:
                self.call_from_thread(review.update, "[red]Error: Could not load wallet (wrong password?)[/red]")
                return

            # Step 4: Sign with Rust secure signer
            self.call_from_thread(review.update, "Signing (Rust secure memory)...")
            signed_tx = self.transaction_manager.sign_transaction_secure(
                unsigned_tx,
                encrypted_container,
                password
            )
            if not signed_tx:
                self.call_from_thread(review.update, "[red]Error: Signing failed (wrong password?)[/red]")
                return

            # Step 5: Broadcast
            self.call_from_thread(review.update, "Broadcasting...")
            tx_base64 = base64.b64encode(signed_tx).decode("utf-8")
            signature = self.network.send_transaction(tx_base64)

            if signature:
                sig_short = f"{signature[:8]}...{signature[-8:]}"
                self.call_from_thread(
                    review.update,
                    f"[green]Sent! Sig: {sig_short}[/green]"
                )
                # Refresh balances after a short delay
                import time
                time.sleep(2)
                self.call_from_thread(self.refresh_data)
            else:
                self.call_from_thread(review.update, "[red]Transaction rejected by network[/red]")

        except Exception as e:
            self.call_from_thread(review.update, f"[red]Error: {str(e)[:60]}[/red]")

    def action_quit(self) -> None:
        """Quit the application (confirm unmount)"""
        if self.usb_manager.mount_point:
            self.push_screen(ConfirmUnmountScreen())
        else:
            self.exit()

    def action_refresh(self) -> None:
        """Manual refresh"""
        self.refresh_data()

    def action_copy_address(self) -> None:
        """Copy public key to clipboard"""
        if not self.current_public_key:
            self.notify("No wallet loaded", severity="warning")
            return
        try:
            import subprocess
            subprocess.run(["pbcopy"], input=self.current_public_key.encode(), check=True)
            self.notify(f"Copied: {self.current_public_key[:8]}...{self.current_public_key[-8:]}", title="Address Copied")
        except Exception:
            try:
                import pyperclip
                pyperclip.copy(self.current_public_key)
                self.notify(f"Copied: {self.current_public_key[:8]}...{self.current_public_key[-8:]}", title="Address Copied")
            except Exception:
                self.notify("Copy failed - select address manually", severity="error")

    def _tx_explorer_link(self, signature: str) -> str:
        base = f"https://explorer.solana.com/tx/{signature}"
        if "devnet" in SOLANA_RPC_URL:
            return f"{base}?cluster=devnet"
        if "testnet" in SOLANA_RPC_URL:
            return f"{base}?cluster=testnet"
        return base

    def action_copy_tx_link(self) -> None:
        """Copy explorer link for selected transaction"""
        panel = self.query_one(TransactionHistoryPanel)
        signature = panel.get_selected_signature()
        if not signature:
            self.notify("No transaction selected", severity="warning")
            return
        link = self._tx_explorer_link(signature)
        try:
            import subprocess
            subprocess.run(["pbcopy"], input=link.encode(), check=True)
            self.notify("Transaction link copied", title="Tx Link")
        except Exception:
            try:
                import pyperclip
                pyperclip.copy(link)
                self.notify("Transaction link copied", title="Tx Link")
            except Exception:
                self.notify("Copy failed - link shown in details", severity="error")

    def action_unmount(self) -> None:
        """Unmount the wallet and exit the TUI"""
        if self.usb_manager.mount_point:
            try:
                self.usb_manager.unmount_device()
                self.did_unmount = True
                self.current_public_key = None
                self.current_balance = 0.0
                self.current_tokens = []
                self.notify("Wallet unmounted", title="Unmounted")
            except Exception:
                self.notify("Failed to unmount", severity="error")
                return
        else:
            self.notify("No wallet mounted", severity="warning")
            return

        # Exit back to main menu
        self.exit()


class ConfirmUnmountScreen(ModalScreen):
    """Confirm unmount before quitting"""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("Unmount wallet and quit?", id="confirm-text"),
            Horizontal(
                Button("Yes, unmount", id="confirm-yes", variant="error"),
                Button("Cancel", id="confirm-no", variant="default"),
            ),
            id="confirm-container"
        )

    def on_mount(self) -> None:
        self.query_one("#confirm-yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.app.action_unmount()
            self.dismiss()
        elif event.button.id == "confirm-no":
            self.dismiss()


class DevicePanel(Static):
    """Right panel - USB device selection"""

    can_focus = True

    BINDINGS = [
        Binding("up", "select_prev", "Previous device", show=False),
        Binding("down", "select_next", "Next device", show=False),
    ]

    devices = reactive([])
    selected_index = reactive(None)

    def compose(self) -> ComposeResult:
        yield Static(" USB DEVICES", classes="panel-header")
        yield Static("", id="device-list")
        yield Static("[dim]Use ↑/↓ to select[/dim]", id="device-hint")

    def watch_devices(self, devices: list) -> None:
        self.refresh_list()

    def watch_selected_index(self, index: Optional[int]) -> None:
        self.refresh_list()

    def refresh_list(self) -> None:
        content = self.query_one("#device-list", Static)
        text = Text()
        if not self.devices:
            text.append("\nNo USB devices detected\n", style="dim")
        else:
            for i, d in enumerate(self.devices[:9], start=1):
                label = d.get("model", "USB").strip() or "USB"
                dev = d.get("device", "")
                size = d.get("size", "")
                is_sel = (self.selected_index == (i - 1))
                row_style = "on #1e3a5f" if is_sel else ""
                text.append(f"\n{i}. ", style=f"bold {row_style}".strip())
                text.append(f"{label} ", style=f"cyan {row_style}".strip())
                text.append(f"{dev} {size}", style=f"dim {row_style}".strip())
        content.update(text)


class NetworkPanel(Static):
    """Right panel - Network status + Devnet airdrop"""

    def compose(self) -> ComposeResult:
        yield Static(" NETWORK", classes="panel-header")
        yield Container(
            Static("", id="network-info"),
            Static("", id="network-extra"),
            Static("", id="airdrop-status"),
            Label("Devnet Airdrop (max 2 SOL):"),
            Horizontal(
                Input(placeholder="1.0", id="airdrop-amount"),
                Button("Request", id="btn-airdrop", variant="success"),
            ),
            id="network-container"
        )

    def on_mount(self) -> None:
        info = self.query_one("#network-info", Static)
        info.update(f"RPC: {SOLANA_RPC_URL}")
        self.query_one("#airdrop-status", Static).update("")

        if "devnet" not in SOLANA_RPC_URL:
            btn = self.query_one("#btn-airdrop", Button)
            btn.disabled = True
            self.query_one("#airdrop-amount", Input).disabled = True
            self.query_one("#airdrop-status", Static).update(
                "[dim]Airdrops only available on Devnet[/dim]"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "btn-airdrop":
            return
        if "devnet" not in SOLANA_RPC_URL:
            self.query_one("#airdrop-status", Static).update(
                "[red]Airdrops only available on Devnet[/red]"
            )
            return

        amt_str = self.query_one("#airdrop-amount", Input).value.strip() or "1.0"
        try:
            amount = float(amt_str)
        except ValueError:
            self.query_one("#airdrop-status", Static).update("[red]Invalid amount[/red]")
            return
        if amount <= 0:
            self.query_one("#airdrop-status", Static).update("[red]Amount must be > 0[/red]")
            return
        if amount > 2:
            amount = 2.0

        self.query_one("#airdrop-status", Static).update(
            f"[yellow]Requesting {amount:.2f} SOL airdrop...[/yellow]"
        )
        self.app.request_airdrop(amount)

    class DeviceSelected(Message):
        """Emitted when a device is selected via arrows"""
        def __init__(self, index: int):
            super().__init__()
            self.index = index

    def action_select_prev(self) -> None:
        if not self.devices:
            return
        if self.selected_index is None:
            self.selected_index = 0
        elif self.selected_index > 0:
            self.selected_index -= 1
        self.post_message(self.DeviceSelected(self.selected_index))

    def action_select_next(self) -> None:
        if not self.devices:
            return
        if self.selected_index is None:
            self.selected_index = 0
        elif self.selected_index < len(self.devices) - 1:
            self.selected_index += 1
        self.post_message(self.DeviceSelected(self.selected_index))

def main():
    """Run the live wallet TUI"""
    app = ColdstarLiveWallet()
    app.run()

if __name__ == "__main__":
    main()
