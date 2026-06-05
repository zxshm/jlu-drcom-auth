# JLU DrCOM Auto Authentication

Linux DrCOM UDP auto-authentication service for campus networks. It can wait for a configured WiFi connection, log in to the DrCOM server, and keep the session alive with periodic heartbeat packets.

## Features

- Connects to an existing NetworkManager WiFi profile.
- Performs DrCOM UDP challenge/login.
- Keeps the authenticated session alive.
- Retries automatically when WiFi, server reachability, or heartbeat fails.
- Supports systemd deployment.
- Keeps credentials out of the repository through environment variables.

## Requirements

- Linux
- Python 3
- NetworkManager with `nmcli`
- A WiFi connection profile already saved on the machine

## Configuration

Copy `.env.example` to a private file such as `/etc/jlu-drcom-auth.env` and fill in the values:

```sh
sudo install -m 600 .env.example /etc/jlu-drcom-auth.env
sudo editor /etc/jlu-drcom-auth.env
```

Required variables:

- `DRCOM_WIFI_SSID`
- `DRCOM_WIFI_IFACE`
- `DRCOM_SERVER`
- `DRCOM_USERNAME`
- `DRCOM_PASSWORD`
- `DRCOM_REGISTERED_MAC`

`DRCOM_REGISTERED_MAC` accepts a 12-digit hex MAC address, with or without `:` separators.

For local manual runs, source a private env file first:

```sh
set -a
. /etc/jlu-drcom-auth.env
set +a
python3 drcom_auth.py
```

## systemd

Install the service file and enable it:

```sh
sudo mkdir -p /opt/jlu-drcom-auth
sudo cp drcom_auth.py /opt/jlu-drcom-auth/
sudo cp jlu-drcom-auth.service /etc/systemd/system/jlu-drcom-auth.service
sudo systemctl daemon-reload
sudo systemctl enable --now jlu-drcom-auth.service
```

Check logs:

```sh
journalctl -u jlu-drcom-auth.service -f
```

The script also writes a local log file by default: `drcom_auth.log`.

## Security

Do not commit real credentials, MAC addresses, IP cache files, or logs. This repository intentionally ignores `.env`, `*.env`, `.drcom_ip_cache`, `*.log`, and Python cache files.
