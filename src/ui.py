"""
Terminal UI Components using Rich library

B - Love U 3000
"""

from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.text import Text
from rich.box import ROUNDED, DOUBLE
from rich import print as rprint
import questionary
from questionary import Style

console = Console()

CUSTOM_STYLE = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'bold'),
    ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
    ('separator', 'fg:gray'),
    ('instruction', 'fg:gray'),
    ('text', ''),
    ('disabled', 'fg:gray italic'),
])


def print_banner():
    banner_text = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║      ███████╗ ██████╗ ██╗      █████╗ ███╗   ██╗ █████╗       ║
║      ██╔════╝██╔═══██╗██║     ██╔══██╗████╗  ██║██╔══██╗      ║
║      ███████╗██║   ██║██║     ███████║██╔██╗ ██║███████║      ║
║      ╚════██║██║   ██║██║     ██╔══██║██║╚██╗██║██╔══██║      ║
║      ███████║╚██████╔╝███████╗██║  ██║██║ ╚████║██║  ██║      ║
║      ╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝      ║
║                                                               ║
║           COLD WALLET USB TOOL v1.1.0 By </Syrem>             ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  SECURITY NOTICE: This tool creates offline Solana wallets.   ║
║  Private keys are stored ONLY on the USB device and NEVER     ║
║  transmitted over the network.                                ║
╚═══════════════════════════════════════════════════════════════╝
"""
    console.print(Text(banner_text, style="cyan"))


def print_success(message: str):
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str):
    console.print(f"[red]✗[/red] [red]{message}[/red]")


def print_warning(message: str):
    console.print(f"[yellow]⚠[/yellow] [yellow]{message}[/yellow]")


def print_info(message: str):
    console.print(f"[cyan]→[/cyan] {message}")


def print_step(step: int, total: int, message: str):
    console.print(f"[cyan][{step}/{total}][/cyan] {message}")


def print_section_header(title: str):
    console.print()
    console.print(Panel(title, style="cyan", box=ROUNDED))
    console.print()


def print_wallet_info(public_key: str, balance: Optional[float] = None):
    table = Table(box=DOUBLE, show_header=False, border_style="cyan")
    table.add_column("Field", style="dim")
    table.add_column("Value", style="green bold")
    
    table.add_row("Public Key", public_key)
    if balance is not None:
        table.add_row("Balance", f"{balance:.9f} SOL")
    
    panel = Panel(
        table,
        title="[bold cyan]WALLET PUBLIC KEY (Safe to Share)[/bold cyan]",
        border_style="cyan",
        box=DOUBLE
    )
    console.print(panel)


def print_transaction_summary(from_addr: str, to_addr: str, amount: float, fee: float = 0.000005):
    table = Table(box=ROUNDED, show_header=False, border_style="yellow")
    table.add_column("Field", style="dim")
    table.add_column("Value", style="bold")
    
    table.add_row("From", from_addr)
    table.add_row("To", to_addr)
    table.add_row("Amount", f"[green]{amount:.9f} SOL[/green]")
    table.add_row("Network Fee", f"[yellow]{fee:.9f} SOL[/yellow]")
    table.add_row("Total", f"[red]{(amount + fee):.9f} SOL[/red]")
    
    panel = Panel(
        table,
        title="[bold yellow]TRANSACTION SUMMARY[/bold yellow]",
        border_style="yellow",
        box=ROUNDED
    )
    console.print(panel)


def print_device_list(devices: list):
    if not devices:
        print_warning("No USB devices detected")
        return
    
    table = Table(title="Detected USB Devices", box=ROUNDED, border_style="cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Device", style="cyan")
    table.add_column("Size", style="green")
    table.add_column("Model", style="yellow")
    table.add_column("Mount Point", style="magenta")
    
    for i, device in enumerate(devices, 1):
        table.add_row(
            str(i),
            device.get('device', 'Unknown'),
            device.get('size', 'Unknown'),
            device.get('model', 'Unknown'),
            device.get('mountpoint', 'Not mounted')
        )
    
    console.print(table)


def confirm_dangerous_action(message: str, confirm_text: str = "CONFIRM") -> bool:
    console.print()
    console.print(Panel(
        f"[red bold]WARNING: {message}[/red bold]\n\n"
        f"This action is IRREVERSIBLE.\n"
        f"Type '[yellow]{confirm_text}[/yellow]' to proceed:",
        title="[red]DANGER ZONE[/red]",
        border_style="red",
        box=DOUBLE
    ))
    
    response = questionary.text(
        "",
        style=CUSTOM_STYLE
    ).ask()
    
    return response == confirm_text


def select_menu_option(options: list, message: str = "Select an option:") -> str:
    return questionary.select(
        message,
        choices=options,
        style=CUSTOM_STYLE
    ).ask()


def get_text_input(message: str, default: str = "") -> str:
    return questionary.text(
        message,
        default=default,
        style=CUSTOM_STYLE
    ).ask()


def get_password_input(message: str) -> str:
    return questionary.password(
        message,
        style=CUSTOM_STYLE
    ).ask()


def get_float_input(message: str, default: float = 0.0) -> float:
    while True:
        try:
            value = questionary.text(
                message,
                default=str(default),
                style=CUSTOM_STYLE
            ).ask()
            return float(value)
        except (ValueError, TypeError):
            print_error("Please enter a valid number")


def create_spinner(description: str):
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console
    )


def create_progress_bar(description: str):
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    )


def print_explorer_link(signature: str, network: str = "mainnet-beta"):
    base_url = "https://explorer.solana.com/tx"
    cluster_param = f"?cluster={network}" if network != "mainnet-beta" else ""
    url = f"{base_url}/{signature}{cluster_param}"
    console.print(f"\n[cyan]View on Solana Explorer:[/cyan]")
    console.print(f"[link={url}]{url}[/link]\n")


def clear_screen():
    console.clear()
