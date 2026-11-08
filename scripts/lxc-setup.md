# Proxmox LXC setup

Replace `<proxmox-host>`, `<ct-id>`, `<template-storage>`, `<disk-storage>`,
`<bridge>`, `<repository-url>` and `<tailnet>` with your own values. Run host
commands as root on the Proxmox host and container commands as root inside the
LXC. Network access is required for installation and image builds.

## Create the container (Proxmox host)

1. Log in to `<proxmox-host>`. Download a Debian 13 standard container template
   using the Proxmox UI's `<template-storage>` → CT Templates → Templates.
2. Create an **unprivileged** Debian 13 LXC with ID `<ct-id>`, hostname
   `notion-dash`, 1 vCPU, 512 MB RAM and a 4 GB disk on `<disk-storage>`.
   Select `<bridge>` and configure networking with working DNS and internet
   access. Enable **Start at boot**.
3. While the container is stopped, enable nesting and keyctl:

   ```sh
   pct set <ct-id> --features nesting=1,keyctl=1
   ```

4. Add these lines to `/etc/pve/lxc/<ct-id>.conf` for Tailscale's TUN device:

   ```text
   lxc.cgroup2.devices.allow: c 10:200 rwm
   lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
   ```

5. Start the container and open a shell:

   ```sh
   pct start <ct-id>
   pct enter <ct-id>
   ```

## Install Docker and Tailscale (inside the LXC)

Install prerequisites and Docker's Debian apt repository:

```sh
apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: trixie
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

Install Tailscale using its official installer, then authenticate. The owner
opens the login URL printed by `tailscale up` and approves the machine:

```sh
curl -fsSL https://tailscale.com/install.sh -o /tmp/tailscale-install.sh
sh /tmp/tailscale-install.sh
systemctl enable --now tailscaled
tailscale up --hostname notion-dash
```

## Configure and start the app (inside the LXC)

```sh
install -d -m 0755 /opt/notion-dash
git clone <repository-url> /opt/notion-dash/app
cd /opt/notion-dash/app
(umask 077; cp .env.example /opt/notion-dash/.env)
chmod 600 /opt/notion-dash/.env
```

Edit `/opt/notion-dash/.env` on the server using the integration token and all
six data source IDs from the [README Deploy section](../README.md#deploy).
Keep this file outside the clone; paste the token directly into the server's
editor and keep it out of chat, shell history and version control.

```sh
docker compose up -d --build
docker compose ps
docker compose exec app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5).read().decode())"
tailscale serve --bg 8000
tailscale serve status
```

The health response should report `"status":"ok"` with an empty `missing`
list. A degraded response means one or more data sources could not be loaded;
check their IDs and integration connections before continuing. The container
healthcheck checks HTTP reachability, so inspect the response body too.

If prompted, the owner enables HTTPS/Serve for the tailnet. Open
`https://notion-dash.<tailnet>.ts.net` from a device on the tailnet. Compose
publishes only on LXC loopback; Tailscale Serve supplies HTTPS. The app trusts
forwarded proxy headers, so keep the loopback binding and use Serve for access.

## Updates

Inside the LXC:

```sh
cd /opt/notion-dash/app
./scripts/deploy.sh
```

This pulls with `--ff-only`, rebuilds and restarts the service, and displays
Compose status. If the checkout has diverged, resolve it before retrying.
