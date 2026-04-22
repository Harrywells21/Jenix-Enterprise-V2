#!/bin/bash
# Run this on your JENIX server to generate client install one-liners

SERVER_IP="${1:-your.server.ip}"
API_KEY="${2:-your_api_key}"

echo ""
echo "=== JENIX Enterprise — Client Install Commands ==="
echo ""
echo "--- Linux (paste as root) ---"
echo "curl -fsSL http://$SERVER_IP:8000/install/linux | JENIX_SERVER=http://$SERVER_IP:8000 JENIX_API_KEY=$API_KEY bash"
echo ""
echo "--- macOS (paste as admin) ---"
echo "curl -fsSL http://$SERVER_IP:8000/install/macos | JENIX_SERVER=http://$SERVER_IP:8000 JENIX_API_KEY=$API_KEY bash"
echo ""
echo "--- Windows (run in Admin PowerShell) ---"
echo "irm http://$SERVER_IP:8000/install/windows | iex"
echo ""
