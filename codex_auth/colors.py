import os
import sys


class Palette:
    def __init__(self) -> None:
        mode = os.environ.get("CODEX_AUTH_COLOR", "auto")
        enabled = False
        if mode == "always":
            enabled = True
        elif mode in ("auto", ""):
            enabled = (
                sys.stdout.isatty()
                and not os.environ.get("NO_COLOR")
                and os.environ.get("TERM") != "dumb"
            )

        self.enabled = enabled
        self.reset = "\033[0m" if enabled else ""
        self.bold = "\033[1m" if enabled else ""
        self.dim = "\033[2m" if enabled else ""
        self.red = "\033[31m" if enabled else ""
        self.green = "\033[32m" if enabled else ""
        self.yellow = "\033[33m" if enabled else ""
        self.blue = "\033[34m" if enabled else ""
        self.cyan = "\033[36m" if enabled else ""

    def text(self, color: str, value: str) -> str:
        if self.enabled and color:
            return f"{color}{value}{self.reset}"
        return value

    def status(self, value: str) -> str:
        if value == "ok":
            return self.green
        if value in ("limited", "unknown"):
            return self.yellow
        if value in ("unusable", "error", "missing"):
            return self.red
        if value == "unchecked":
            return self.dim
        return ""

    def percent_left(self, value: str) -> str:
        try:
            pct = int(value.rstrip("%"))
        except ValueError:
            return ""
        if pct >= 50:
            return self.green
        if pct >= 20:
            return self.yellow
        return self.red
