"""
ui/fix_view.py
──────────────
Fix Engine view for JENIX.
Provides UI for: fix_packages, install_missing, update_system
"""

import threading
import tkinter as tk
from tkinter import ttk

from core.fix_engine import fix_packages, install_missing, update_system


class FixView(tk.Frame):
    """View for package repair and system updates (Fix Engine)."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#0f0f0f")
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Title
        tk.Label(
            self,
            text="🔧  FIX ENGINE",
            font=("Courier New", 16, "bold"),
            fg="#00aaff",
            bg="#0f0f0f",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(16, 4))

        tk.Label(
            self,
            text="Package repair, dependency installation & system updates",
            font=("Courier New", 9),
            fg="#555555",
            bg="#0f0f0f",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 12))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=4)

        # Buttons
        btn_frame = tk.Frame(self, bg="#0f0f0f")
        btn_frame.pack(fill="x", padx=16, pady=10)

        actions = [
            ("🔩  Fix Packages",      fix_packages,    "#00aaff"),
            ("📦  Install Missing",   install_missing, "#aa66ff"),
            ("🔄  Update System",     update_system,   "#00ffcc"),
        ]

        for col, (label, fn, color) in enumerate(actions):
            btn = tk.Button(
                btn_frame,
                text=label,
                font=("Courier New", 10, "bold"),
                fg=color,
                bg="#1a1a1a",
                activebackground="#2a2a2a",
                activeforeground=color,
                relief="flat",
                bd=0,
                padx=12,
                pady=8,
                cursor="hand2",
                command=lambda f=fn: self._run(f),
            )
            btn.grid(row=0, column=col, padx=6, pady=4, sticky="ew")
            btn_frame.columnconfigure(col, weight=1)

        # Warning note
        warn = tk.Label(
            self,
            text="⚠  These operations require elevated privileges (sudo/root).",
            font=("Courier New", 8),
            fg="#aa6600",
            bg="#0f0f0f",
            anchor="w",
        )
        warn.pack(fill="x", padx=20, pady=(0, 4))

        # Status
        self._status_var = tk.StringVar(value="● idle")
        tk.Label(
            self,
            textvariable=self._status_var,
            font=("Courier New", 9),
            fg="#555555",
            bg="#0f0f0f",
            anchor="w",
        ).pack(fill="x", padx=20, pady=(2, 2))

        # Output
        out_frame = tk.Frame(self, bg="#0f0f0f")
        out_frame.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self._output = tk.Text(
            out_frame,
            bg="#0a0a0a",
            fg="#cccccc",
            font=("Courier New", 10),
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
            state="disabled",
            wrap="word",
            highlightthickness=1,
            highlightbackground="#2a2a2a",
        )
        scrollbar = ttk.Scrollbar(out_frame, orient="vertical", command=self._output.yview)
        self._output.configure(yscrollcommand=scrollbar.set)
        self._output.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str = "#555555"):
        self._status_var.set(text)

    def _write(self, text: str):
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.insert("end", text)
        self._output.configure(state="disabled")

    def _run(self, fn):
        self._set_status("● running…", "#ffaa00")
        self._write("Running — this may take a moment…")
        threading.Thread(target=self._execute, args=(fn,), daemon=True).start()

    def _execute(self, fn):
        try:
            result = fn()
        except Exception as exc:
            self.after(0, self._display_error, str(exc))
            return
        self.after(0, self._display_result, result)

    def _display_result(self, result: dict):
        ok = result.get("success", False)
        msg = result.get("message", "")
        data = result.get("data", {})

        lines = [
            f"{'✔  SUCCESS' if ok else '✘  FAILED'}",
            f"{'─' * 48}",
            f"Message : {msg}",
            "",
        ]

        affected = data.get("affected_packages", [])
        actions  = data.get("actions_taken", [])

        if actions:
            lines.append("Actions taken:")
            for a in actions:
                lines.append(f"  • {a}")
            lines.append("")

        if affected:
            lines.append(f"Affected packages ({len(affected)}):")
            for pkg in affected[:30]:
                lines.append(f"  • {pkg}")
            if len(affected) > 30:
                lines.append(f"  … and {len(affected) - 30} more")

        self._write("\n".join(lines))
        self._set_status(f"● {'success' if ok else 'failed'}", "#00aaff" if ok else "#ff4444")

    def _display_error(self, msg: str):
        self._write(f"✘  EXCEPTION\n{'─' * 48}\n{msg}")
        self._set_status("● error", "#ff4444")
