"""
Token Logo Fetcher and Terminal Image Renderer
Supports Kitty and iTerm2 inline image protocols
NO FALLBACKS - Real images only
"""

import base64
import os
import sys
from pathlib import Path
from io import BytesIO
from typing import Optional

try:
    from PIL import Image
    import requests
except ImportError:
    Image = None
    requests = None

# Token logo URLs (from Solana token list and official sources)
TOKEN_LOGOS = {
    "SOL": "https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/So11111111111111111111111111111111111111112/logo.png",
    "USDC": "https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v/logo.png",
    "USDT": "https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB/logo.png",
    "RAY": "https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R/logo.png",
    "BONK": "https://arweave.net/hQiPZOsRZXGXBJd_82PhVdlM_hACsT_q6wqwf5cSY7I",
    "JUP": "https://static.jup.ag/jup/icon.png",
}

class TokenLogoManager:
    """Fetch and render token logos in terminal - Real images only, no fallbacks"""

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = Path.home() / ".coldstar" / "token_logos"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Detect terminal type
        self.terminal_type = self._detect_terminal()

    def _detect_terminal(self) -> str:
        """Detect which terminal emulator is being used"""
        term = os.environ.get("TERM", "")
        term_program = os.environ.get("TERM_PROGRAM", "")

        if "kitty" in term.lower():
            return "kitty"
        elif term_program == "iTerm.app":
            return "iterm2"
        else:
            return "unsupported"

    def supports_images(self) -> bool:
        """Check if current terminal supports inline images"""
        return self.terminal_type in ["kitty", "iterm2"]

    def fetch_logo(self, symbol: str) -> Optional[Path]:
        """Fetch and cache a token logo - Returns None if fails"""
        if not Image or not requests:
            return None

        url = TOKEN_LOGOS.get(symbol)
        if not url:
            return None

        # Create cache filename
        cache_file = self.cache_dir / f"{symbol.lower()}.png"

        # Return cached if exists
        if cache_file.exists():
            return cache_file

        # Download logo
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # Resize to small size for terminal (20x20 for better visibility)
                img = Image.open(BytesIO(response.content))
                img = img.convert("RGBA")
                img.thumbnail((20, 20), Image.Resampling.LANCZOS)

                # Save to cache
                img.save(cache_file, "PNG")
                return cache_file
        except Exception as e:
            # Silent fail - no fallback
            pass

        return None

    def render_image_kitty(self, image_path: Path) -> str:
        """Render image using Kitty graphics protocol"""
        if not image_path.exists():
            return ""

        try:
            # Read and encode image
            with open(image_path, "rb") as f:
                img_data = base64.standard_b64encode(f.read()).decode("ascii")

            # Kitty graphics protocol
            # a=T: transmit and display, f=100: PNG format, t=f: direct transmission
            return f"\033_Ga=T,f=100,t=f;{img_data}\033\\ "
        except:
            return ""

    def render_image_iterm2(self, image_path: Path) -> str:
        """Render image using iTerm2 inline images protocol"""
        if not image_path.exists():
            return ""

        try:
            # Read and encode image
            with open(image_path, "rb") as f:
                img_data = base64.standard_b64encode(f.read()).decode("ascii")

            # iTerm2 inline image protocol
            # inline=1: inline display, width/height in cells
            return f"\033]1337;File=inline=1;width=2;height=1:{img_data}\007"
        except:
            return ""

    def get_token_icon(self, symbol: str) -> str:
        """
        Get token icon - ONLY real image, NO fallbacks
        Returns empty string if terminal doesn't support images or fetch fails
        """
        if not self.supports_images():
            return ""  # No fallback

        # Try to fetch and render logo
        logo_path = self.fetch_logo(symbol)
        if not logo_path:
            return ""  # No fallback

        if self.terminal_type == "kitty":
            return self.render_image_kitty(logo_path)
        elif self.terminal_type == "iterm2":
            return self.render_image_iterm2(logo_path)

        return ""  # No fallback

    def preload_common_tokens(self):
        """Preload logos for common tokens in background"""
        for symbol in ["SOL", "USDC", "USDT", "RAY", "BONK", "JUP"]:
            self.fetch_logo(symbol)
