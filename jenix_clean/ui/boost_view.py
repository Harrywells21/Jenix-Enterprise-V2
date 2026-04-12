"""
ui/boost_view.py
────────────────
Boost Engine view for JENIX.
Provides UI for: gaming_mode, work_mode, deep_clean, preview_clean
"""

import threading
import tkinter as tk
from tkinter import ttk

from core.boost_engine import gaming_mode, work_mode, deep_clean, preview_clean


class BoostView(tk.Frame):
    """View for system optimisation (Boost Engine)."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#0f0f0f")
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Title
        title = tk.Label(
            self,
            text="⚡  BOOST ENGINE",
            font=("Courier New", 16, "bold"),
            fg="#00ff99",
            bg="#0f0f0f",
            anchor="w",
        )
        title.pack(fill="x", padx=16, pady=(16, 4))

        subtitle = tk.Label(
            self,
            text="System optimisation & performance controls",
            font=("Courier New", 9),
            fg="#555555",
            bg="#0f0f0f",
            anchor="w",
        )
        subtitle.pack(fill="x", padx=16, pady=(0, 12))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=4)

        # Button grid
        btn_frame = tk.Frame(self, bg="#0f0f0f")
        btn_frame.pack(fill="x", padx=16, pady=10)

        actions = [
            ("🎮  Gaming Mode",   gaming_mode,   "#00ff99"),
            ("💼  Work Mode",     work_mode,     "#00aaff"),
            ("🧹  Deep Clean",    deep_clean,    "#ff6600"),
            ("🔍  Preview Clean", preview_clean, "#aaaaaa"),
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

        # Status indicator
        self._status_var = tk.StringVar(value="● idle")
        status_label = tk.Label(
            self,
            textvariable=self._status_var,
            font=("Courier New", 9),
            fg="#555555",
            bg="#0f0f0f",
            anchor="w",
        )
        status_label.pack(fill="x", padx=20, pady=(4, 2))

        # Output display
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
        # Locate the status label and recolour it
        for child in self.winfo_children():
            if isinstance(child, tk.Label) and child.cget("textvariable") == str(self._status_var):
                child.configure(fg=color)
                break

    def _write(self, text: str):
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.insert("end", text)
        self._output.configure(state="disabled")

    def _run(self, fn):
        self._set_status("● running…", "#ffaa00")
        self._write("Running…")
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

        lines = []
        lines.append(f"{'✔  SUCCESS' if ok else '✘  FAILED'}")
        lines.append(f"{'─' * 48}")
        lines.append(f"Message : {msg}")
        lines.append("")

        for key, val in data.items():
            if isinstance(val, list):
                lines.append(f"{key} ({len(val)}):")
                for item in val[:20]:
                    lines.append(f"  • {item}")
                if len(val) > 20:
                    lines.append(f"  … and {len(val) - 20} more")
            else:
                lines.append(f"{key} : {val}")

        self._write("\n".join(lines))
        color = "#00ff99" if ok else "#ff4444"
        self._set_status(f"● {'success' if ok else 'failed'}", color)

    def _display_error(self, msg: str):
        self._write(f"✘  EXCEPTION\n{'─' * 48}\n{msg}")
        self._set_status("● error", "#ff4444")
