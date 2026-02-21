"""
Coldstar TUI (Text User Interface) - Modern Dashboard
Built with Textual for a rich terminal experience
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Button, Input, Label, DataTable, Select
from textual.binding import Binding
from textual import events
from rich.text import Text
from datetime import datetime
from typing import Optional

class StatusBar(Static):
    """Top status bar showing wallet info"""

    def __init__(self, wallet_name: str = "usb-03", mode: str = "OFFLINE SIGNING", network: str = "mainnet"):
        super().__init__()
        self.wallet_name = wallet_name
        self.mode = mode
        self.network = network
        self.last_sync = "2m ago"
        self.warnings = 0
        self.total_value = "$12,431"
        self.change_24h = "+1.8%"

    def render(self) -> Text:
        text = Text()
        text.append("COLDSTAR", style="bold cyan")
        text.append(" • ", style="dim")
        text.append(f"Vault: {self.wallet_name}", style="white")
        text.append(" • ", style="dim")
        text.append(self.mode, style="yellow bold")
        text.append(" • ", style="dim")
        text.append(f"RPC: {self.network}", style="cyan")
        return text

class InfoBar(Static):
    """Second bar with sync status and portfolio value"""

    def __init__(self):
        super().__init__()
        self.last_sync = "2m ago"
        self.warnings = 0
        self.total_value = "$12,431"
        self.change_24h = "+1.8%"

    def render(self) -> Text:
        text = Text()
        text.append(f"Last sync {self.last_sync}", style="dim")
        text.append(" • ", style="dim")
        text.append(f"{self.warnings} warnings", style="yellow" if self.warnings > 0 else "dim")
        text.append(" • ", style="dim")
        text.append(f"Total {self.total_value}", style="bold green")
        text.append(" • ", style="dim")
        text.append(f"24h {self.change_24h}", style="green" if "+" in self.change_24h else "red")
        return text

class PortfolioPanel(Static):
    """Left panel - Portfolio token list"""

    def compose(self) -> ComposeResult:
        yield Label("Portfolio")

        portfolio_static = Static(self._render_portfolio())
        content = ScrollableContainer(portfolio_static)
        yield content

    def _render_portfolio(self) -> Text:
        tokens = [
            {"icon": "🔵", "symbol": "SOL", "amount": "3.2546", "value": "476.80"},
            {"icon": "🔵", "symbol": "USDC", "amount": "1,025.00", "value": "1,025.00"},
            {"icon": "🟠", "symbol": "BTC", "amount": "0.0125", "value": "600.50"},
            {"icon": "🟡", "symbol": "RAY", "amount": "500.0", "value": "85.00"},
            {"icon": "🟣", "symbol": "XYZ", "amount": "10,000", "value": "0.00"},
            {"icon": "🟡", "symbol": "Unknown Token", "amount": "10,000", "value": "0.00"},
        ]

        text = Text()
        for token in tokens:
            text.append(f"\n{token['icon']} ", style="")
            text.append(f"{token['symbol']:<15}", style="bold white")
            text.append(f"{token['amount']:>12}", style="cyan")
            text.append(f"  {token['value']:>8}", style="green")

        return text

class DetailsPanel(Static):
    """Middle panel - Transaction details/history"""

    def compose(self) -> ComposeResult:
        yield Label("USDC Details")

        details_static = Static(self._render_details())
        content = ScrollableContainer(details_static)
        yield content

    def _render_details(self) -> Text:
        text = Text()
        text.append("Mint: EPjFW...DeF2", style="dim")
        text.append(" • Decimals: 6", style="dim")
        text.append(" • Verified SPL Token\n\n", style="green")

        text.append("- ", style="green")
        text.append("Received 500.00 USDC", style="white")
        text.append("  30m ago\n", style="dim")

        text.append("- ", style="yellow")
        text.append("Sent 250.00 USDC", style="white")
        text.append("      2h ago\n", style="dim")

        text.append("- ", style="green")
        text.append("Received 775.00 USDC", style="white")
        text.append("   1d ago\n\n", style="dim")

        text.append("Risk Notes:\n\n", style="yellow bold")
        text.append("• Transfer-hook enabled\n", style="dim")
        text.append("• Direct transfer • Swap then send\n", style="dim")

        return text

class SendPanel(Static):
    """Right panel - Send transaction form"""

    def compose(self) -> ComposeResult:
        yield Label("Send USDC")
        yield Container(
            Label("To:"),
            Input(placeholder="4xp...Tf8Y"),
            Label("Amount:"),
            Horizontal(
                Input(value="100.00"),
                Button("max"),
                Static("[25% 50% 75% 100%]")
            ),
            Label("Fee:"),
            Horizontal(
                Button("[Standard]"),
                Button("Fast"),
                Button("Custom")
            ),
            Static("Network fee ~0.000005 SOL • You'll have 3.15 SOL left"),
            Label("Review:"),
            Static(self._render_review()),
            Static("Press [ENTER] to confirm:"),
            Horizontal(
                Button("[ENTER] Send", variant="success"),
                Button("[x] Cancel")
            )
        )

    def _render_review(self) -> Text:
        text = Text()
        text.append("- USDC   100.00\n", style="white")
        text.append("- To:    4xp..Tf8Y\n", style="dim")
        text.append("  Expected fee: ~0.000005 SOL", style="dim")
        return text

class BottomBar(Static):
    """Bottom shortcuts bar"""

    def render(self) -> Text:
        text = Text()
        text.append("/ Search", style="dim")
        text.append(" • ", style="dim")
        text.append("Tab Sort", style="dim")
        text.append(" • ", style="dim")
        text.append("Space Multi-select", style="dim")
        text.append(" • ", style="dim")
        text.append("Arrows navigate", style="dim")
        text.append(" • ", style="dim")
        text.append("a = max", style="dim")
        text.append(" • ", style="dim")
        text.append("1|2|3|4 = % split", style="dim")
        return text

class ColdstarTUI(App):
    """Main Coldstar TUI Application"""

    CSS = """
    Screen {
        background: $surface;
    }

    .status-bar {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    .info-bar {
        dock: top;
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }

    .main-container {
        height: 100%;
    }

    .panel-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    .panel-content {
        height: 100%;
    }

    .bottom-bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }

    PortfolioPanel {
        width: 1fr;
        border: solid $primary;
        padding: 1;
    }

    DetailsPanel {
        width: 1fr;
        border: solid $primary;
        padding: 1;
        margin-left: 1;
    }

    SendPanel {
        width: 1fr;
        border: solid $primary;
        padding: 1;
        margin-left: 1;
    }

    .send-form {
        height: auto;
    }

    .field-label {
        margin-top: 1;
        color: $text-muted;
    }

    .amount-row, .fee-row {
        height: auto;
        margin: 1 0;
    }

    .amount-input {
        width: 1fr;
    }

    .max-btn {
        width: auto;
        margin-left: 1;
    }

    .amount-presets {
        margin-left: 1;
        color: $text-muted;
    }

    .fee-btn {
        margin-right: 1;
    }

    .fee-btn.active {
        background: $accent;
        color: $text;
    }

    .fee-info {
        color: $text-muted;
        margin: 1 0;
    }

    .review-label {
        margin-top: 2;
    }

    .review-box {
        border: solid $accent;
        padding: 1;
        margin: 1 0;
    }

    .confirm-prompt {
        color: $success;
        margin: 1 0;
    }

    .action-buttons {
        height: auto;
    }

    .send-btn {
        width: 1fr;
        margin-right: 1;
    }

    .cancel-btn {
        width: auto;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        ("1", "percent_25", "25%"),
        ("2", "percent_50", "50%"),
        ("3", "percent_75", "75%"),
        ("4", "percent_100", "100%"),
        ("a", "max", "Max"),
        ("/", "search", "Search"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        status_bar = StatusBar()
        status_bar.add_class("status-bar")
        yield status_bar

        info_bar = InfoBar()
        info_bar.add_class("info-bar")
        yield info_bar

        main = Horizontal(
            PortfolioPanel(),
            DetailsPanel(),
            SendPanel()
        )
        main.add_class("main-container")
        yield main

        bottom_bar = BottomBar()
        bottom_bar.add_class("bottom-bar")
        yield bottom_bar

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_percent_25(self) -> None:
        """Set amount to 25%"""
        # TODO: Implement
        pass

    def action_percent_50(self) -> None:
        """Set amount to 50%"""
        # TODO: Implement
        pass

    def action_percent_75(self) -> None:
        """Set amount to 75%"""
        # TODO: Implement
        pass

    def action_percent_100(self) -> None:
        """Set amount to 100%"""
        # TODO: Implement
        pass

    def action_max(self) -> None:
        """Set amount to max"""
        # TODO: Implement
        pass

    def action_search(self) -> None:
        """Open search"""
        # TODO: Implement
        pass

def run_tui():
    """Run the TUI application"""
    app = ColdstarTUI()
    app.run()

if __name__ == "__main__":
    run_tui()
