"""
utils/logger.py
───────────────
Centralised logging for JENIX — production-grade, thread-safe GUI integration.

Usage:
    from utils.logger import log, set_gui_callback, write_forensic_file, audit

    # Once the GUI window exists:
    set_gui_callback(app.update_log_panel)

    log.info("System scan started")
    log.warning("Low disk space")
    log.success("Boost applied")
    log.forensic("Suspicious port 4444")
    audit("boost", "Applied CPU governor: performance")
    write_forensic_file("port_scan.txt", "port 4444 open\n")
"""

from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# ── Paths ─────────────────────────────────────────────────────────────────────

_BASE        = Path.home() / ".jenix"
LOG_DIR      = _BASE / "logs"
FORENSIC_DIR = LOG_DIR / "forensics"
LOG_FILE     = LOG_DIR / "jenix.log"
AUDIT_LOG    = LOG_DIR / "audit.log"

for _p in (LOG_DIR, FORENSIC_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# ── Custom levels ─────────────────────────────────────────────────────────────

SUCCESS_LEVEL  = 25   # INFO < SUCCESS < WARNING
FORENSIC_LEVEL = 35   # WARNING < FORENSIC < ERROR

logging.addLevelName(SUCCESS_LEVEL,  "SUCCESS")
logging.addLevelName(FORENSIC_LEVEL, "FORENSIC")

# ── GUI callback (thread-safe registry) ───────────────────────────────────────

_gui_lock: threading.Lock             = threading.Lock()
_gui_callback: Optional[Callable]    = None


def set_gui_callback(fn: Callable[[str, str], None]) -> None:
    """
    Register a callable(message: str, level: str) that updates the GUI panel.
    The callable must itself schedule any Tk operations via after(0, ...).
    Safe to call from any thread; safe to call multiple times (replaces old cb).
    """
    global _gui_callback
    with _gui_lock:
        _gui_callback = fn


def _dispatch_gui(message: str, level: str) -> None:
    """Forward a log line to the GUI callback. Never raises."""
    with _gui_lock:
        cb = _gui_callback
    if cb is not None:
        try:
            cb(message, level)
        except Exception:
            pass


# ── Forensic file helper ───────────────────────────────────────────────────────

def write_forensic_file(filename: str, content: str) -> Path:
    """
    Write content to ~/.jenix/logs/forensics/<filename>.
    Also dispatches a FORENSIC-level GUI log entry.
    Returns the Path written.
    """
    dest = FORENSIC_DIR / filename
    try:
        dest.write_text(content, encoding="utf-8")
    except OSError as exc:
        _dispatch_gui(f"write_forensic_file failed: {exc}", "ERROR")
        return dest
    _dispatch_gui(f"Forensic file written: {dest.name}", "FORENSIC")
    return dest


def _auto_forensic_file(message: str) -> None:
    """Auto-create a timestamped forensic file when log.forensic() is called."""
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    fname = f"forensic_{ts}.txt"
    body  = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] FORENSIC\n{message}\n"
    write_forensic_file(fname, body)


# ── Audit helper ───────────────────────────────────────────────────────────────

def audit(action_type: str, description: str, metadata: Optional[dict] = None) -> None:
    """Append a structured audit entry to audit.log and dispatch to GUI."""
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [AUDIT   ] [{action_type[:16]}] {description}"
    if metadata:
        line += " | " + ", ".join(f"{k}={v}" for k, v in metadata.items())
    try:
        with AUDIT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    _dispatch_gui(description, "AUDIT")


# ── Formatter ─────────────────────────────────────────────────────────────────

class _JenixFormatter(logging.Formatter):
    _LABEL = {
        "DEBUG":    "DBG ",
        "INFO":     "INFO",
        "WARNING":  "WARN",
        "SUCCESS":  "OK  ",
        "ERROR":    "ERR ",
        "FORENSIC": "FRNS",
        "CRITICAL": "CRIT",
        "AUDIT":    "AUDT",
    }
    _ANSI = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[0m",
        "WARNING":  "\033[33m",
        "SUCCESS":  "\033[32m",
        "ERROR":    "\033[31m",
        "FORENSIC": "\033[35m",
        "CRITICAL": "\033[1;31m",
    }
    _RESET = "\033[0m"

    def __init__(self, use_colour: bool = False) -> None:
        super().__init__()
        self._use_colour = use_colour

    def format(self, record: logging.LogRecord) -> str:
        ts    = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname
        label = self._LABEL.get(level, level[:4].ljust(4))
        msg   = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            msg = f"{msg}\n{record.exc_text}"
        line = f"[{ts}] [{label}] {msg}"
        if self._use_colour:
            colour = self._ANSI.get(level, "")
            return f"{colour}{line}{self._RESET}"
        return line


# ── GUI handler ────────────────────────────────────────────────────────────────

class _GUIHandler(logging.Handler):
    """Forwards every log record to the registered GUI callback (non-blocking)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _dispatch_gui(record.getMessage(), record.levelname)
        except Exception:
            self.handleError(record)


# ── Custom level methods injected onto Logger ──────────────────────────────────

def _success(self: logging.Logger, message: object, *args, **kwargs) -> None:
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)


def _forensic(self: logging.Logger, message: object, *args, **kwargs) -> None:
    if self.isEnabledFor(FORENSIC_LEVEL):
        self._log(FORENSIC_LEVEL, message, args, **kwargs)
        # Auto-create forensic file on a daemon thread so we never block
        threading.Thread(
            target=_auto_forensic_file,
            args=(str(message),),
            daemon=True,
        ).start()


logging.Logger.success  = _success   # type: ignore[attr-defined]
logging.Logger.forensic = _forensic  # type: ignore[attr-defined]


# ── Build the singleton logger ─────────────────────────────────────────────────

def _build() -> logging.Logger:
    logger = logging.getLogger("jenix")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # File: everything
    try:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_JenixFormatter(use_colour=False))
        logger.addHandler(fh)
    except OSError:
        pass

    # Audit file: WARNING +
    try:
        ah = logging.FileHandler(AUDIT_LOG, encoding="utf-8")
        ah.setLevel(logging.WARNING)
        ah.setFormatter(_JenixFormatter(use_colour=False))
        logger.addHandler(ah)
    except OSError:
        pass

    # Console: INFO +
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    ch.setFormatter(_JenixFormatter(use_colour=tty))
    logger.addHandler(ch)

    # GUI: everything
    gh = _GUIHandler()
    gh.setLevel(logging.DEBUG)
    logger.addHandler(gh)

    return logger


log: logging.Logger = _build()
