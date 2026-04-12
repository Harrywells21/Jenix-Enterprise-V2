"""
ui/rollback_view.py
───────────────────
Rollback Engine view for JENIX.
Placeholder UI — backend not yet implemented.
"""

import tkinter as tk
from tkinter import ttk


class RollbackView(tk.Frame):
    """Placeholder view for system rollback functionality."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#0f0f0f")
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        tk.Label(
            self,
            text="↩  ROLLBACK ENGINE",
            font=("Courier New", 16, "bold"),
            fg="#cc88ff",
            bg="#0f0f0f",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(16, 4))

        tk.Label(
            self,
            text="Restore system state from snapshots and checkpoints",
            font=("Courier New", 9),
            fg="#555555",
            bg="#0f0f0f",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 12))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=4)

        # Placeholder action buttons
        btn_frame = tk.Frame(self, bg="#0f0f0f")
        btn_frame.pack(fill="x", padx=16, pady=10)

        placeholder_actions = [
            ("📸  Create Snapshot",   "#cc88ff"),
            ("📋  List Snapshots",    "#aaaaaa"),
            ("↩  Restore Snapshot",  "#ffaa66"),
            ("🗑  Delete Snapshot",  "#ff6666"),
        ]

        for col, (label, color) in enumerate(placeholder_actions):
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
                state="disabled",
                disabledforeground="#444444",
            )
            btn.grid(row=0, column=col, padx=6, pady=4, sticky="ew")
            btn_frame.columnconfigure(col, weight=1)

        # "Coming soon" notice
        notice_frame = tk.Frame(self, bg="#1a1a1a", padx=16, pady=16)
        notice_frame.pack(fill="x", padx=16, pady=(8, 12))

        tk.Label(
            notice_frame,
            text="🚧  Backend Not Yet Implemented",
            font=("Courier New", 12, "bold"),
            fg="#cc88ff",
            bg="#1a1a1a",
        ).pack(pady=(0, 8))

        features = [
            "Automatic pre-operation snapshots",
            "Timestamped restore points",
            "Package state rollback (apt/dnf/pacman)",
            "Configuration file history",
            "Diff viewer for snapshot comparison",
        ]

        for feat in features:
            tk.Label(
                notice_frame,
                text=f"  ○  {feat}",
                font=("Courier New", 9),
                fg="#777777",
                bg="#1a1a1a",
                anchor="w",
            ).pack(fill="x", pady=1)

        # Status
        tk.Label(
            self,
            text="● coming soon",
            font=("Courier New", 9),
            fg="#555555",
            bg="#0f0f0f",
            anchor="w",
        ).pack(fill="x", padx=20, pady=6)

        # Empty output area (consistent layout)
        out_frame = tk.Frame(self, bg="#0f0f0f")
        out_frame.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        output = tk.Text(
            out_frame,
            bg="#0a0a0a",
            fg="#444444",
            font=("Courier New", 10),
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
            state="disabled",
            wrap="word",
            highlightthickness=1,
            highlightbackground="#222222",
        )
        output.configure(state="normal")
        output.insert(
            "end",
            "Rollback engine output will appear here once the backend is implemented.\n"
            "Snapshots will be listed and managed from this panel.",
        )
        output.configure(state="disabled")
        output.pack(side="left", fill="both", expand=True)
