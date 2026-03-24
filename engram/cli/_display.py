"""
ENGRAM OS CLI - Shared display utilities.

All visual output goes through these functions.
No command prints directly — always uses these helpers.
"""

import sys
import time
import shutil
import threading
from typing import Optional


ENGRAM_BANNER = """
  ███████╗███╗   ██╗ ██████╗ ██████╗  █████╗ ███╗   ███╗
  ██╔════╝████╗  ██║██╔════╝ ██╔══██╗██╔══██╗████╗ ████║
  █████╗  ██╔██╗ ██║██║  ███╗██████╔╝███████║██╔████╔██║
  ██╔══╝  ██║╚██╗██║██║   ██║██╔══██╗██╔══██║██║╚██╔╝██║
  ███████╗██║ ╚████║╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
  ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
  """

COLORS = {
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "red":    "\033[91m",
    "blue":   "\033[94m",
    "cyan":   "\033[96m",
    "gray":   "\033[90m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
}

# Detect if terminal supports color
USE_COLOR = sys.stdout.isatty()


def color(text: str, c: str) -> str:
    """Apply ANSI color to text."""
    if not USE_COLOR:
        return text
    return f"{COLORS.get(c, '')}{text}{COLORS['reset']}"


def ok(msg: str, detail: str = "") -> None:
    """Print success message with checkmark."""
    prefix = color("  ✓", "green")
    line = f"{prefix} {msg}"
    if detail:
        line += color(f" — {detail}", "gray")
    try:
        print(line)
    except UnicodeEncodeError:
        # Fallback to ASCII for Windows console
        print(f"  [OK] {msg}")


def fail(msg: str, fix: str = "") -> None:
    """Print failure message with X mark."""
    prefix = color("  ✗", "red")
    line = f"{prefix} {msg}"
    try:
        print(line)
        if fix:
            print(color(f"    → Fix: {fix}", "yellow"))
    except UnicodeEncodeError:
        # Fallback to ASCII for Windows console
        print(f"  [FAIL] {msg}")
        if fix:
            print(f"    -> Fix: {fix}")


def warn(msg: str, detail: str = "") -> None:
    """Print warning message with warning icon."""
    prefix = color("  ⚠", "yellow")
    line = f"{prefix} {msg}"
    if detail:
        line += color(f" — {detail}", "gray")
    try:
        print(line)
    except UnicodeEncodeError:
        # Fallback to ASCII for Windows console
        print(f"  [WARN] {msg}")


def info(msg: str) -> None:
    """Print informational message in gray."""
    try:
        print(color(f"  {msg}", "gray"))
    except UnicodeEncodeError:
        print(f"  {msg}")


def section(title: str) -> None:
    """Print section header."""
    width = shutil.get_terminal_size((80, 20)).columns
    print()
    print(color(f"  {title}", "bold"))
    try:
        print(color("  " + "─" * min(50, width - 2), "gray"))
    except UnicodeEncodeError:
        # Fallback to ASCII for Windows console
        print(color("  " + "-" * min(50, width - 2), "gray"))


def banner() -> None:
    """Print ENGRAM banner."""
    try:
        print(color(ENGRAM_BANNER, "cyan"))
        print(color(
            "  Cognitive OS for autonomous long-horizon AI execution",
            "gray"
        ))
    except UnicodeEncodeError:
        print("  ENGRAM OS")
        print("  Cognitive OS for autonomous long-horizon AI execution")
    print()


def divider() -> None:
    """Print horizontal divider line."""
    width = shutil.get_terminal_size((80, 20)).columns
    try:
        print(color("  " + "═" * min(50, width - 2), "gray"))
    except UnicodeEncodeError:
        # Fallback to ASCII for Windows console
        print(color("  " + "=" * min(50, width - 2), "gray"))


def header(title: str, subtitle: str = "") -> None:
    """Print command header with title and optional subtitle."""
    divider()
    try:
        print(color(f"  ENGRAM OS — {title}", "bold"))
    except UnicodeEncodeError:
        print(f"  ENGRAM OS - {title}")
    if subtitle:
        print(color(f"  {subtitle}", "gray"))
    divider()


def footer(status: str, message: str = "") -> None:
    """Print command footer with status."""
    divider()
    try:
        if status == "ok":
            print(color(f"  ✓ {message}", "green"))
        elif status == "warn":
            print(color(f"  ⚠ {message}", "yellow"))
        else:
            print(color(f"  ✗ {message}", "red"))
    except UnicodeEncodeError:
        if status == "ok":
            print(f"  [OK] {message}")
        elif status == "warn":
            print(f"  [WARN] {message}")
        else:
            print(f"  [FAIL] {message}")
    divider()
    print()


class ProgressBar:
    """
    Simple terminal progress bar.

    Usage:
        bar = ProgressBar(total=100, label="Processing")
        for i in range(100):
            bar.update(i+1, suffix="file.py")
        bar.done("Complete")
    """

    def __init__(self, total: int, label: str = "",
                 width: int = 30) -> None:
        self.total = max(1, total)
        self.label = label
        self.width = width
        self._start = time.time()

    def update(self, current: int, suffix: str = "") -> None:
        """Update progress bar with current position and optional suffix."""
        pct = min(1.0, current / self.total)
        filled = int(self.width * pct)
        bar = "█" * filled + "░" * (self.width - filled)
        elapsed = time.time() - self._start
        pct_str = f"{int(pct * 100):3d}%"
        suffix_str = suffix[:30].ljust(30) if suffix else ""
        line = (
            f"\r  [{bar}] {pct_str}"
            f" {current}/{self.total}"
            f" — {suffix_str}"
        )
        if USE_COLOR:
            sys.stdout.write(color(line, "cyan"))
        else:
            sys.stdout.write(line)
        sys.stdout.flush()

    def done(self, message: str = "Done") -> None:
        """Complete the progress bar with final message."""
        bar = "█" * self.width
        elapsed = time.time() - self._start
        line = (
            f"\r  [{bar}] 100%"
            f" {self.total}/{self.total}"
            f" — {message}"
            f" ({elapsed:.1f}s)\n"
        )
        sys.stdout.write(color(line, "green") if USE_COLOR else line)
        sys.stdout.flush()


class Spinner:
    """
    Terminal spinner for operations with unknown duration.

    Usage:
        with Spinner("Loading model..."):
            time.sleep(3)
    """

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "") -> None:
        self.message = message
        self._thread = None
        self._running = False
        self._lock = threading.Lock()

    def __enter__(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._spin, daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        with self._lock:
            sys.stdout.write(f"\r{' ' * 60}\r")
            sys.stdout.flush()

    def _spin(self):
        i = 0
        try:
            while self._running:
                frame = self.FRAMES[i % len(self.FRAMES)]
                with self._lock:
                    sys.stdout.write(
                        f"\r  {color(frame, 'cyan')} {self.message}"
                    )
                    sys.stdout.flush()
                time.sleep(0.1)
                i += 1
        except Exception:
            # Silently ignore errors during spinner cleanup
            pass
