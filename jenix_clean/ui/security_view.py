"""
ui/security_view.py
───────────────────
Security Engine view for JENIX.
Provides UI for: scan_ports, classify_risk
"""

import threading
import tkinter as tk
from tkinter import ttk

from core.security_engine import scan_ports, classify_risk


# Risk tier colours
_RISK_COLORS = {
    "green":  "#00ff99",
    "yellow": "#ffcc00",
    "red":    "#ff4444",
}


class SecurityView(tk.Frame):
    """View for network security scanning (Security Engine)."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#0f0f0f")
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        tk.Label(
            self,
            text="🛡  SECURITY ENGINE",
            font=("Courier New", 16, "bold"),
            fg="#ff4444",
            bg="#0f0f0f",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(16, 4))

        tk.Label(
            self,
            text="Port scanning and network risk classification",
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
            ("🔍  Scan Ports",      scan_ports,    "#aaaaaa"),
            ("⚠  Classify Risk",   classify_risk, "#ff4444"),
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

        # Summary bar (shown after scan)
        self._summary_frame = tk.Frame(self, bg="#0f0f0f")
        self._summary_frame.pack(fill="x", padx=16, pady=(0, 4))

        self._green_lbl  = self._make_badge(self._summary_frame, "● 0 green",  "#00ff99")
        self._yellow_lbl = self._make_badge(self._summary_frame, "● 0 yellow", "#ffcc00")
        self._red_lbl    = self._make_badge(self._summary_frame, "● 0 red",    "#ff4444")
        for lbl in (self._green_lbl, self._yellow_lbl, self._red_lbl):
            lbl.pack(side="left", padx=(0, 12))

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

        # Output text
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
        # Tag colours for risk tiers
        for tier, color in _RISK_COLORS.items():
            self._output.tag_configure(tier, foreground=color)

        scrollbar = ttk.Scrollbar(out_frame, orient="vertical", command=self._output.yview)
        self._output.configure(yscrollcommand=scrollbar.set)
        self._output.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    @staticmethod
    def _make_badge(parent, text, color):
        return tk.Label(
            parent,
            text=text,
            font=("Courier New", 9, "bold"),
            fg=color,
            bg="#0f0f0f",
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str = "#555555"):
        self._status_var.set(text)

    def _clear_output(self):
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")

    def _append(self, text: str, tag: str = ""):
        self._output.configure(state="normal")
        if tag:
            self._output.insert("end", text, tag)
        else:
            self._output.insert("end", text)

    def _seal_output(self):
        self._output.configure(state="disabled")

    def _run(self, fn):
        self._set_status("● scanning…", "#ffaa00")
        self._clear_output()
        self._append("Scanning — please wait…")
        self._seal_output()
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
        ports = data.get("ports", [])
        risk_summary = data.get("risk_summary", {})

        # Update badge counts
        self._green_lbl.config(text=f"● {risk_summary.get('green', 0)} green")
        self._yellow_lbl.config(text=f"● {risk_summary.get('yellow', 0)} yellow")
        self._red_lbl.config(text=f"● {risk_summary.get('red', 0)} red")

        self._clear_output()

        header = (
            f"{'✔  SUCCESS' if ok else '✘  FAILED'}\n"
            f"{'─' * 56}\n"
            f"Message : {msg}\n\n"
        )
        self._append(header)

        if ports:
            # Column header
            self._append(f"{'PORT':<8}{'PROTO':<8}{'PROCESS':<22}{'PID':<8}")
            if "risk" in ports[0]:
                self._append("RISK\n")
            else:
                self._append("\n")
            self._append(f"{'─' * 56}\n")

            for p in ports:
                line = (
                    f"{p['port']:<8}"
                    f"{p['proto']:<8}"
                    f"{p['process']:<22}"
                    f"{p['pid']:<8}"
                )
                risk = p.get("risk", "")
                if risk:
                    self._append(line)
                    self._append(f"{risk.upper()}\n", risk)
                else:
                    self._append(line + "\n")

        self._seal_output()
        self._set_status(
            f"● {'success' if ok else 'failed'} — {len(ports)} port(s)",
            "#00ff99" if ok else "#ff4444",
        )

    def _display_error(self, msg: str):
        self._clear_output()
        self._append(f"✘  EXCEPTION\n{'─' * 48}\n{msg}")
        self._seal_output()
        self._set_status("● error", "#ff4444")
