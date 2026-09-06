# JENIX Agent Installation Guide
Built by Aaditya Singh - aadisingh0121@gmail.com

## Method 1 - One-Line Installer (Recommended)

    curl -sSL http://YOUR_SERVER:8000/install | bash

Replace YOUR_SERVER:8000 with your JENIX server's real address.

The installer will interactively ask for your server address if it isn't
already set. To skip the prompt (e.g. for scripted/unattended installs),
set the JENIX_SERVER environment variable before running it:

    JENIX_SERVER=http://YOUR_SERVER:8000 curl -sSL http://YOUR_SERVER:8000/install | bash

To pre-assign the new machine to a specific site at install time (optional,
for MSP multi-client setups), also set JENIX_SITE_ID:

    JENIX_SERVER=http://YOUR_SERVER:8000 JENIX_SITE_ID=3 curl -sSL http://YOUR_SERVER:8000/install | bash

The installer detects your OS automatically and downloads the correct
pre-built agent binary directly from your JENIX server - no separate
binary distribution step is needed.

## Method 2 - Manual Installation

There is currently no separate raw-source manual install path - the
one-line installer above IS the supported install method. If you want to
inspect the installer before running it (recommended for security-conscious
environments), download and read it first:

    curl -sSL http://YOUR_SERVER:8000/install -o install_jenix.sh
    less install_jenix.sh
    bash install_jenix.sh

## Troubleshooting

Cannot reach server:
    curl http://YOUR_SERVER:8000/health
    sudo ufw allow 8000

Remove agent:
    sudo systemctl stop jenix-agent
    sudo systemctl disable jenix-agent
    sudo rm /etc/systemd/system/jenix-agent.service
    rm -rf ~/.jenix

## Supported OS (today)
- Ubuntu 20.04+
- Linux Mint 21+
- Debian 11+
- CentOS 8+
- Fedora 36+
- Raspberry Pi OS

## Coming Soon
- Windows (native one-line PowerShell installer - in active development)
- macOS (native one-line installer - in active development)

Both are being built and tested on real hardware before release; they are
not yet available in this build. Attempting the Windows installer script
included in this repo will not currently succeed end-to-end.
