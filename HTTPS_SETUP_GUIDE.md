# JENIX Enterprise - HTTPS Setup Guide
Built by Aaditya Singh - aadisingh0121@gmail.com

## Option 1 - Lets Encrypt (Public Server, Free SSL)

    sudo apt-get install certbot python3-certbot-nginx -y
    sudo certbot --nginx -d your-domain.com

## Option 2 - Self-Signed Certificate (Internal/LAN)

    sudo mkdir -p /etc/jenix/ssl
    sudo openssl req -x509 -nodes -days 3650       -newkey rsa:2048       -keyout /etc/jenix/ssl/jenix.key       -out    /etc/jenix/ssl/jenix.crt       -subj "/C=IN/O=YourCompany/CN=jenix.local"

Then update nginx.conf ssl_certificate paths accordingly.

## Option 3 - Run Server Directly with HTTPS

    openssl req -x509 -nodes -days 3650 -newkey rsa:2048       -keyout jenix.key -out jenix.crt -subj "/CN=localhost"

    uvicorn main:app --host 0.0.0.0 --port 8443       --ssl-keyfile jenix.key --ssl-certfile jenix.crt

Then update dashboard api/index.js BASE to use https and wss.

## After Enabling HTTPS

Update agent installations:
    curl -sSL https://YOUR_SERVER/install.sh | bash -s -- --server https://YOUR_SERVER

Update agent .env:
    JENIX_SERVER=https://YOUR_SERVER

## Testing

    curl -k https://YOUR_SERVER/health
