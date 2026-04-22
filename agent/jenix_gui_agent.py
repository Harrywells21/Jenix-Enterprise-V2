#!/usr/bin/env python3
"""
JENIX Enterprise Agent — GUI Version
Double-click to run. Auto-discovers server on local network.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import socket
import json
import os
import sys
import time
import asyncio
import platform
import subprocess

# ── Auto-discovery ────────────────────────────────────────────────────────────
COMMON_PORTS = [8000, 8080, 80, 443]
DISCOVERY_TIMEOUT = 2

def discover_server():
    """Scan local network for JENIX server."""
    # First try common local IPs
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "192.168.1.1"
    
    # Build list of IPs to scan
    base = ".".join(local_ip.split(".")[:3])
    candidates = []
    
    # Common gateway IPs first
    for last in [1, 100, 101, 102, 103, 104, 105, 200]:
        candidates.append(f"{base}.{last}")
    
    # Scan all IPs in subnet
    for last in range(1, 255):
        ip = f"{base}.{last}"
        if ip not in candidates:
            candidates.append(ip)

    for ip in candidates:
        for port in COMMON_PORTS:
            try:
                url = f"http://{ip}:{port}/api/agent/ping"
                import urllib.request
                req = urllib.request.urlopen(url, timeout=DISCOVERY_TIMEOUT)
                data = json.loads(req.read())
                if data.get("status") == "ok":
                    return f"http://{ip}:{port}"
            except:
                continue
    return None

# ── GUI ───────────────────────────────────────────────────────────────────────
class JenixAgentGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JENIX Enterprise Agent")
        self.root.geometry("480x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#02040a")
        
        # Center window
        self.root.eval('tk::PlaceWindow . center')
        
        self.server_url = None
        self.connected = False
        self.agent_thread = None
        self.running = False
        
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def _build_ui(self):
        bg = "#02040a"
        card = "#0d1d35"
        blue = "#1a6fff"
        text = "#e8f4ff"
        sub = "#4a7fa5"
        green = "#00ff88"
        red = "#ff4466"
        
        # ── Header ────────────────────────────────────────────────
        header = tk.Frame(self.root, bg="#0a1628", pady=20)
        header.pack(fill="x")
        
        tk.Label(header, text="⬡ JENIX", font=("Helvetica", 22, "bold"),
                bg="#0a1628", fg=blue).pack()
        tk.Label(header, text="ENTERPRISE AGENT", font=("Helvetica", 9),
                bg="#0a1628", fg=sub).pack()
        
        # ── Status card ───────────────────────────────────────────
        status_frame = tk.Frame(self.root, bg=card, pady=16, padx=20)
        status_frame.pack(fill="x", padx=20, pady=(16,8))
        
        tk.Label(status_frame, text="STATUS", font=("Helvetica", 8),
                bg=card, fg=sub).pack(anchor="w")
        
        self.status_dot = tk.Label(status_frame, text="● DISCONNECTED",
                font=("Helvetica", 14, "bold"), bg=card, fg=red)
        self.status_dot.pack(anchor="w", pady=(4,0))
        
        self.status_sub = tk.Label(status_frame, text="Not connected to any JENIX server",
                font=("Helvetica", 9), bg=card, fg=sub)
        self.status_sub.pack(anchor="w")
        
        # ── Server URL ────────────────────────────────────────────
        url_frame = tk.Frame(self.root, bg=card, pady=16, padx=20)
        url_frame.pack(fill="x", padx=20, pady=4)
        
        tk.Label(url_frame, text="SERVER URL", font=("Helvetica", 8),
                bg=card, fg=sub).pack(anchor="w")
        
        entry_frame = tk.Frame(url_frame, bg="#060c18", pady=2)
        entry_frame.pack(fill="x", pady=(4,0))
        
        self.url_entry = tk.Entry(entry_frame, font=("Helvetica", 11),
                bg="#060c18", fg=text, insertbackground=text,
                relief="flat", bd=8)
        self.url_entry.pack(fill="x")
        self.url_entry.insert(0, "http://")
        
        # ── Buttons ───────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=bg, pady=8)
        btn_frame.pack(fill="x", padx=20)
        
        # Auto-discover button
        self.discover_btn = tk.Button(btn_frame,
                text="🔍  Auto-Discover Server",
                font=("Helvetica", 11, "bold"),
                bg="#0a2040", fg=blue,
                relief="flat", bd=0, pady=10,
                cursor="hand2",
                command=self._start_discover)
        self.discover_btn.pack(fill="x", pady=(0,6))
        
        # Connect button
        self.connect_btn = tk.Button(btn_frame,
                text="⚡  Connect",
                font=("Helvetica", 12, "bold"),
                bg=blue, fg="white",
                relief="flat", bd=0, pady=12,
                cursor="hand2",
                command=self._connect)
        self.connect_btn.pack(fill="x")
        
        # ── Log ───────────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg=card, pady=12, padx=16)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(12,0))
        
        tk.Label(log_frame, text="LOG", font=("Helvetica", 8),
                bg=card, fg=sub).pack(anchor="w")
        
        self.log_text = tk.Text(log_frame, font=("Courier", 9),
                bg="#060c18", fg="#4a9f6f",
                relief="flat", bd=4, height=8,
                state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, pady=(4,0))
        
        # ── Machine info ──────────────────────────────────────────
        info_frame = tk.Frame(self.root, bg=bg, pady=8)
        info_frame.pack(fill="x", padx=20, pady=(8,12))
        
        machine = f"{platform.node()} · {platform.system()} {platform.release()}"
        tk.Label(info_frame, text=machine, font=("Helvetica", 8),
                bg=bg, fg=sub).pack()
        
    def _log(self, msg, color="#4a9f6f"):
        def _do():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _do)
    
    def _set_status(self, text, color, sub=""):
        def _do():
            self.status_dot.configure(text=f"● {text}", fg=color)
            if sub:
                self.status_sub.configure(text=sub)
        self.root.after(0, _do)
    
    def _start_discover(self):
        self._log("Scanning local network for JENIX server...")
        self._set_status("SCANNING...", "#ffaa00", "Looking for JENIX server on local network")
        self.discover_btn.configure(state="disabled", text="🔍  Scanning...")
        
        def _scan():
            url = discover_server()
            def _done():
                self.discover_btn.configure(state="normal", text="🔍  Auto-Discover Server")
                if url:
                    self.url_entry.delete(0, "end")
                    self.url_entry.insert(0, url)
                    self._log(f"✓ Found JENIX server at {url}")
                    self._set_status("SERVER FOUND", "#ffaa00", f"Found at {url} — click Connect")
                    messagebox.showinfo("Server Found!", 
                        f"JENIX server found at:\n{url}\n\nClick Connect to link this machine.")
                else:
                    self._log("✗ No server found. Enter URL manually.")
                    self._set_status("NOT FOUND", "#ff4466", "Enter server URL manually below")
                    messagebox.showwarning("Not Found",
                        "Could not auto-discover a JENIX server.\n\n"
                        "Please enter the server URL manually\n"
                        "(e.g. http://192.168.1.100:8000)")
            self.root.after(0, _done)
        
        threading.Thread(target=_scan, daemon=True).start()
    
    def _connect(self):
        url = self.url_entry.get().strip().rstrip("/")
        if not url.startswith("http"):
            messagebox.showerror("Invalid URL", "URL must start with http:// or https://")
            return
        
        self._log(f"Connecting to {url}...")
        self._set_status("CONNECTING...", "#ffaa00", f"Connecting to {url}")
        self.connect_btn.configure(state="disabled", text="Connecting...")
        
        def _do_connect():
            # Test server reachability
            try:
                import urllib.request
                req = urllib.request.urlopen(f"{url}/api/agent/ping", timeout=5)
                data = json.loads(req.read())
                if data.get("status") != "ok":
                    raise Exception("Server not responding correctly")
            except Exception as e:
                def _fail():
                    self._log(f"✗ Cannot reach server: {e}")
                    self._set_status("FAILED", "#ff4466", f"Cannot reach {url}")
                    self.connect_btn.configure(state="normal", text="⚡  Connect")
                    messagebox.showerror("Connection Failed",
                        f"Cannot reach JENIX server at:\n{url}\n\n"
                        f"Error: {e}\n\n"
                        "Make sure:\n"
                        "• Server is running\n"
                        "• URL is correct\n"
                        "• Firewall allows port 8000")
                self.root.after(0, _fail)
                return
            
            # Save config
            config_dir = os.path.expanduser("~/.jenix")
            os.makedirs(config_dir, exist_ok=True)
            with open(os.path.join(config_dir, "config.json"), "w") as f:
                json.dump({"server": url}, f)
            
            # Start agent
            self.server_url = url
            self.running = True
            
            def _success():
                self._log(f"✓ Connected to {url}")
                self._log(f"✓ This machine: {platform.node()}")
                self._log("✓ Sending metrics every 10 seconds...")
                self._set_status("CONNECTED", "#00ff88", f"Connected to {url}")
                self.connect_btn.configure(
                    bg="#0a3020", fg="#00ff88",
                    text="✓ Connected — Running in background",
                    state="disabled"
                )
                self.discover_btn.configure(state="disabled")
            self.root.after(0, _success)
            
            # Run the actual agent
            agent_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jenix_agent.py")
            if os.path.exists(agent_path):
                self._run_agent_loop(url, agent_path)
            else:
                self._log("✗ Agent script not found next to this file")
        
        threading.Thread(target=_do_connect, daemon=True).start()
    
    def _run_agent_loop(self, url, agent_path):
        """Run the agent as a subprocess and monitor its output."""
        while self.running:
            try:
                proc = subprocess.Popen(
                    [sys.executable, agent_path, "--server", url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        self._log(line)
                proc.wait()
                if self.running:
                    self._log("Agent disconnected. Reconnecting in 10s...")
                    time.sleep(10)
            except Exception as e:
                self._log(f"Agent error: {e}")
                time.sleep(10)
    
    def _on_close(self):
        if self.connected:
            if messagebox.askyesno("Quit?", 
                "If you close this window, the agent will stop\n"
                "and your machine will go offline in the dashboard.\n\n"
                "Are you sure you want to quit?"):
                self.running = False
                self.root.destroy()
        else:
            self.running = False
            self.root.destroy()
    
    def run(self):
        # Load saved config
        config_path = os.path.expanduser("~/.jenix/config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    config = json.load(f)
                    saved_url = config.get("server", "")
                    if saved_url:
                        self.url_entry.delete(0, "end")
                        self.url_entry.insert(0, saved_url)
                        self._log(f"Loaded saved server: {saved_url}")
            except:
                pass
        
        self._log(f"JENIX Agent started on {platform.node()}")
        self._log(f"OS: {platform.system()} {platform.release()}")
        self._log("Click 'Auto-Discover' or enter server URL manually")
        self.root.mainloop()

if __name__ == "__main__":
    app = JenixAgentGUI()
    app.run()
