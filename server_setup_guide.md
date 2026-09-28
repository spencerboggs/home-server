# The Server - Setup Guide

https://github.com/spencerboggs/home-server.git

This is the ordered procedure for the machine described in `README.md`: Ubuntu, Tailscale, the firewall, the VLAN, and Docker.

`README.md` is the design. Follow this guide from section 0 through section 11. Stop at the first step that fails, fix it, then continue.

When `docker run hello-world` works, stop and follow `repo_setup_guide.md`. That guide clones this repository, starts the services, and checks that a browser anywhere on the internet can reach the dashboard. Sections 13 onward in this file are the requirements those scripts are carrying out.

Do not deploy every application on day one. The server is staged on purpose.

Two things this build has to satisfy:

1. One private-cloud frontend, with individual accounts.
2. The server sits on its own network. If it is compromised, the attacker gets the server, not the rest of the home network.

---

# 0. What You Are Building

```text
                              INTERNET
                                  |
                           Cloudflare / DNS
                                  |
                            HTTPS 80 / 443
                                  |
                         +----------------+
                         | Caddy Reverse  |
                         |     Proxy      |
                         +--------+-------+
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             +-------------+              +-------------+
             |  Authentik  |              |   Unified   |
             | SSO / RBAC  |              |  Dashboard  |
             +-------------+              +-------------+
                                  |
                         Docker services behind Caddy
                                  |
          vLLM, websites, Minecraft, Jellyfin, Forgejo,
          Nextcloud, Coolify, monitoring, and the rest
```

```text
                              INTERNET
                                  |
                           Cloudflare / DNS
                                  |
                           Home Router / NAT
                                  |
                         +--------v--------+
                         |    OPNsense    |
                         |    Firewall    |
                         +--------+--------+
                                  |
                         SERVER VLAN / DMZ
                                  |
                         +--------v--------+
                         |  Ubuntu Server  |
                         |  UFW + Docker   |
                         |  Caddy + Apps   |
                         +--------+--------+
                                  |
                         Internet: ALLOWED
                         Home LAN: BLOCKED

Admin access: Tailscale -> Ubuntu Server
```

Normally the only ports forwarded from the internet are:

```text
80/tcp       HTTP
443/tcp      HTTPS
25565/tcp    Minecraft, if enabled
```

Do not expose SSH, Docker, databases, vLLM or any other inference API, Redis, or internal admin panels directly to the internet.

---

# 1. What You Need

## This machine

The server is an HP Z820 with an NVIDIA Titan, 128 GB of RAM, and two SSDs. One memory slot is faulty. Find that slot and leave it empty before you trust the machine with Docker or accounts. A NAS may be added later. This guide does not set one up. These two disks are the only storage.

People use the site from anywhere in a browser, each with their own account. Administrators and programmers SSH from other networks through Tailscale. Port 22 is not forwarded.

## Hardware

- The Z820 stays on, on a wired Ethernet port
- Two SSDs, each at least 1 TB:
  - The NVMe on the PCIe adapter holds Ubuntu, Docker, and databases. The Z820 has no onboard M.2 slot, so this disk only exists because of that adapter. In the installer it is `nvme0n1`.
  - The SSD in a drive bay holds media, models, Minecraft, Nextcloud files, and the shared library. In the installer it is an `sd` disk, not `nvme`. Leave it empty until `repo_setup_guide.md` formats it.
- 128 GB of RAM, with one slot that must stay empty after you identify it
- The Titan in a PCIe x16 slot, powered by the workstation's own PCIe power leads

Install Ubuntu on the NVMe only. The setup script treats whichever disk holds `/` as the fast disk and can format the other empty disk as bulk storage.

## Internet

You need a home connection where you can forward ports, and a public IPv4 address (or a plan for getting inbound 80/443/25565 to this machine).

### Check for CGNAT

On your normal PC:

1. Search `what is my IP`.
2. Log into the router and find the WAN/Internet IP.
3. Compare the two addresses.

If they differ, you are likely behind CGNAT. Port forwarding will not reach this server until the ISP provides a public address or you otherwise have a working inbound path. Tailscale administration still works either way. Do not continue to the public HTTPS and Minecraft steps until inbound 80/443 works.

## Accounts and names to have ready

- A domain you control, with DNS on Cloudflare
- A Tailscale account
- The Linux host username you will create during Ubuntu setup
- The initial Authentik administrator accounts you will create during Authentik setup

The Linux login and the Authentik accounts are different. SSH belongs to the Linux account and is reached through Tailscale. People who use the dashboard, media, git, and chat get Authentik accounts. Regular Authentik users never receive SSH.

---

# 2. Download Ubuntu Server

Use Ubuntu Server 24.04 LTS.

https://ubuntu.com/download/server

You do not need Ubuntu Desktop.

---

# 3. Create the Ubuntu USB

On Windows, download Rufus:

https://rufus.ie/

Use an empty USB drive (8 GB or larger).

1. Device: the USB drive
2. Boot selection: the Ubuntu Server ISO
3. Start
4. Accept Rufus defaults unless it asks something you do not recognize

Rufus erases the USB.

---

# 4. Install Ubuntu Server

Power on and press Esc for the startup menu. F9 chooses the boot device. F10 opens Computer Setup. Boot the USB from F9.

Watch the memory count on the HP logo screen. 128 GB is the full set. A lower number, or a 927 or 929 message that names `CPU0` or `CPU1` and a DIMM slot, is the faulty slot. Write that label down. Press F1 only to get past the warning so you can install. You will pull that DIMM in the next section.

During installation:

- Use Ethernet and DHCP for now. The permanent address comes from a DHCP reservation, then from the server VLAN.
- On the disk screen, install Ubuntu on the NVMe (`nvme0n1`, the PCIe adapter). Do not select the bay SSD. The setup script formats that second disk later.
- If the two disks are hard to tell apart, switch to a shell from the installer and run `lsblk`. The NVMe is the install target. The `sd` disk stays untouched.
- Create a normal Linux administrative account with a long unique password. Example: name `Spencer`, server name `homeserver`, username `spencer`. Do not use a short or reused password. This login is only for SSH. Website accounts are created later and are not this user.
- Install OpenSSH Server when asked.

Finish, reboot, and remove the USB.

---

# 5. First Login

On the server:

```bash
ip addr
```

Write down the current address. From Windows:

```powershell
ssh spencer@192.168.1.123
```

Use your Linux username and the address you actually saw.

## Leave the bad memory slot empty

Do this before updates, Docker, or the public site. A bad slot will corrupt data if you keep using it.

The Z820 holds memory on two riser cards, one for each CPU. HP labels slots `CPU0 DIMM 1` through `CPU0 DIMM 8` and the same for `CPU1`. The POST screen and the label on the riser use those names.

On the server:

```bash
free -h
sudo dmidecode -t memory
sudo dmesg -T | grep -iE 'EDAC|hardware error|DIMM|memory error' || true
```

`dmidecode` prints each stick: size, locator, manufacturer, and serial. `free -h` shows a bit less than the installed total, because the kernel reserves some. If POST already named a slot, find that same locator here.

Then power off. Unplug the power cord. Press the power button once so the supply drains. Open the side panel and pull the riser for the CPU named in the error. Release the DIMM latches and remove the stick in the named slot. Leave that slot empty. Do not move another stick into it.

If POST did not name a slot, use the locators from `dmidecode` and remove one stick at a time from the suspected riser. Boot, read `free -h` and `dmesg`, and stop when the errors are gone. Write the empty locator on a note and leave it in the chassis.

Boot again and confirm:

```bash
free -h
sudo dmidecode -t memory | grep -E 'Size:|Locator:'
sudo dmesg -T | grep -iE 'EDAC|hardware error|DIMM|memory error' || true
```

The empty slot should show `Size: No Module Installed`. The remaining RAM should be 128 GB minus the size of the stick you removed. A 16 GB stick leaves about 112 GB. An 8 GB stick leaves about 120 GB. `free -h` prints a little less than that. The `dmesg` search should print nothing.

Run one Memtest86+ pass before you put services on the machine.

```bash
sudo apt update
sudo apt install -y memtest86+
sudo reboot
```

Choose Memtest86+ from the GRUB menu. Let one pass finish. Power off if it reports errors, and repeat the locator steps for the new slot. Then boot Ubuntu again.

---

# 6. Reserve a LAN Address

Do this on the router or OPNsense, not inside Ubuntu. A reservation based on the server MAC address is easier to recover than a static address configured only on the host.

The server's lasting address is on the server VLAN:

```text
Home LAN:    192.168.1.0/24
Server VLAN: 192.168.50.0/24
Server:      192.168.50.10
```

If the VLAN does not exist yet, reserve the address the server has right now so DHCP does not give it a new one. When you create the VLAN in step 10, move this reservation to `192.168.50.10` and update every SSH command and port forward to that address.

Reboot after saving the reservation and confirm `ip addr` shows the reserved address.

---

# 7. Update Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
sudo reboot
```

SSH back in before continuing.

---

# 8. Install Tailscale

Tailscale is the admin network. Programmers and managers use it from whatever network they are on: home, work, a phone hotspot, or another city. SSH is not published to the internet, and it does not require anyone to be on the home LAN.

https://tailscale.com/docs/install/linux

On the server:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Open the login URL and approve the server. Then:

```bash
tailscale status
tailscale ip -4
```

Each administrator installs Tailscale on their own computer and signs into the same tailnet:

https://tailscale.com/download

Invite them from the Tailscale admin console. A regular user of the website does not get a Tailscale account. The tailnet can reach SSH, so it is only for people who administer the machine.

From any of those computers:

```powershell
ssh spencer@100.100.100.20
```

Use the address printed by `tailscale ip -4`. `tailscale status` also shows a name you can use if MagicDNS is on.

After the repository is on the server, add each programmer's own Linux login and SSH key:

```bash
sudo bash scripts/admin/add-ssh-key.sh alice "ssh-ed25519 AAAA... alice@laptop"
```

That account can `sudo` and run Docker. It is separate from their dashboard login. Keep a working Tailscale SSH session open until you have confirmed a second session from another network.

---

# 9. Configure UFW

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow in on tailscale0 to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 25565/tcp
sudo ufw enable
sudo ufw status verbose
```

Remove the `25565/tcp` rule if Minecraft will not be public.

SSH is allowed on `tailscale0` only. Ports 80 and 443 are allowed from the internet. Port 25565 is allowed only while Minecraft is public.

Docker can open ports past UFW. This repository publishes 80 and 443 from Caddy, and 25565 only when the games profile is on.

Confirm Tailscale SSH from a second window before you close the current session. After the VLAN in the next section, the home LAN cannot reach the server. Tailscale is the path that still works, including for an admin who is not in the house.

---

# 10. Put the Server on Its Own VLAN

Use OPNsense, or another firewall that can enforce VLAN policy. The Ubuntu firewall is a second layer. It is not the boundary that protects the home LAN.

Example:

```text
Home LAN:    192.168.1.0/24
Server VLAN: 192.168.50.0/24
Server:      192.168.50.10
```

Move the server's switch port or SSID onto the server VLAN, then set the DHCP reservation to `192.168.50.10`.

Firewall policy:

```text
Server VLAN -> Internet       ALLOW
Server VLAN -> Home LAN       DENY
Server VLAN -> Other VLANs    DENY
Home LAN -> Server VLAN       DENY by default
Management -> Server VLAN     ALLOW where required
```

The server must not be able to scan, SSH to, mount SMB shares on, or otherwise open connections to normal home devices.

Test all of this before any public application exists:

- From the server, the internet works (`ping` or `curl` to a public site).
- From the server, a host on `192.168.1.0/24` does not respond.
- From a normal home device, the server's admin ports do not respond.
- From an administrator computer on any network, `ssh` over Tailscale still works.
- `ip addr` shows `192.168.50.10`.

Public port forwards, in step 16, are created on this firewall from the WAN to `192.168.50.10`. They are not created on the home LAN.

---

# 11. Install Docker

https://docs.docker.com/engine/install/ubuntu/

Install Docker Engine, the CLI, containerd, Buildx, and the Compose plugin from Docker's official Ubuntu repository. The commands below match Docker's current Ubuntu repository setup. If Docker's page has changed, follow that page.

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Allow the Linux admin user to run Docker, then log out and back in over Tailscale:

```bash
sudo usermod -aG docker $USER
```

Verify:

```bash
docker run hello-world
docker compose version
```

## Titan GPU

Install the driver before `scripts/up.sh ai`. The rest of the server does not need the GPU, so a driver problem does not block the dashboard.

The Z820 can be holding more than one kind of Titan. They do not all run the current vLLM image.

| Card | Chip | What to expect |
|---|---|---|
| GTX Titan, Titan Black, Titan Z | Kepler | The 470 driver series is the last one that supports it. The vLLM image in this repo will not run. Leave the ai profile off. |
| GTX Titan X | Maxwell | The 580 driver series is the last one that supports it. Install that driver, then try the ai profile. If the container exits because the GPU is unsupported, leave the ai profile off. |
| Titan Xp, Titan V | Pascal or Volta | Same as Titan X. Confirm with `nvidia-smi` before you pull the large images. |
| Titan RTX | Turing | Current Ubuntu drivers and the vLLM image can use it. |

Find which card you have after the driver is installed. `nvidia-smi` prints the name and the memory size (6 GB, 12 GB, or 24 GB).

```bash
sudo apt update
sudo apt install -y ubuntu-drivers-common
ubuntu-drivers devices
```

Install the driver package that list recommends for this card. On a Kepler Titan that may be the 470 series. On a Maxwell, Pascal, or Volta Titan, use the 580 series if it is offered, not a newer branch that has dropped those chips. Then:

```bash
sudo reboot
```

SSH back in over Tailscale and confirm the card:

```bash
nvidia-smi
```

The command prints the Titan's name, a driver version, and the memory total. If `nvidia-smi` fails, stop here and fix the driver. Do not start the ai profile.

For a card that is still on a supported driver, install the NVIDIA Container Toolkit from NVIDIA's Ubuntu instructions, then:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

The second `nvidia-smi` has to print the same Titan from inside Docker. That download is the CUDA test image, not a service this repo keeps running. Kepler cards fail this test. That is expected. Skip `scripts/up.sh ai` on those cards.

The dashboard and the LLM containers do not receive the Docker socket. The executor, Promtail, and Coolify are the only containers that mount it, and only for their own jobs.

---

# 12. Hand off to the repository

Docker is the last step in this guide. The dashboard, Caddy, Authentik, disks, and the rest of the applications come from this git repository:

https://github.com/spencerboggs/home-server.git

Open `repo_setup_guide.md` and follow it from the start. The clone command is in that file. Do not clone or run `scripts/setup.sh` from this file.

---

# 13. How services are published

Containers share Docker networks. They do not publish host ports.

The exceptions are:

```text
Caddy          80/tcp, 443/tcp, 443/udp
Minecraft      25565/tcp, only with the games profile
LanCache       port 80 on a second IP, only if you set LANCACHE_BIND_IP
```

Caddy proxies to container names such as `server-dashboard:8000`. A service that is not on the `edge` network cannot be reached from the internet even if a Caddy site block names it. vLLM is on the private network only.

The Docker socket is mounted only by:

- the executor, for the allowlisted actions
- Promtail, read-only, to ship container logs
- Coolify, and only when the deploy profile is on

Do not give it to the dashboard, Jellyfin, Forgejo, Nextcloud, or any LLM container.

---

# 14. Disk layout

`scripts/setup.sh` creates this. You do not need to mkdir it by hand.

```text
NVMe, the disk that holds /
├── /                         Ubuntu
├── /var/lib/docker           images and container layers
└── /srv/server/data/         Authentik, Grafana, Prometheus, Loki, Forgejo, dashboard

Drive-bay SSD, and any disk added later, pooled at /srv/bulk
├── media/{Movies,TV,Music,Photos,Other}
├── models/
├── backups/
├── storage/{downloads,games,software,projects,releases}
├── minecraft/
├── nextcloud/
└── lancache/
```

`/srv/server/media`, `/srv/server/models`, `/srv/server/backups`, and `/srv/server/storage` are symlinks into that pool. Compose files keep using `/srv/bulk` and `/srv/server/data`.

Databases stay on the NVMe. mergerfs is a poor place for Postgres. Media, models, worlds, and Nextcloud files are the bulky sequential data, so they go on the pool.

Quotas and the Prometheus disk alerts apply to both `/` and `/srv/bulk`. Raw SMB or NFS shares are never exposed to the internet.

---

# Caddy

Caddy is the public entry for web applications. HTTP redirects to HTTPS. Passwords, sessions, and application data are never sent in clear text.

This repository builds a Caddy image with the Cloudflare DNS module and runs it as `server-caddy`, publishing only 80 and 443. `scripts/setup.sh` disables the apt Caddy service if you installed one earlier, so the two do not fight over those ports.

The generated file is `runtime/Caddyfile`. It is rebuilt from `.env` and `config/profiles` whenever you run `scripts/up.sh`. Edit `.env`, then:

```bash
sudo bash scripts/up.sh core
```

Hostnames:

```text
dashboard.example.com
auth.example.com
media.example.com
git.example.com
files.example.com
office.example.com
apps.example.com
notify.example.com
grafana.example.com
```

A site block is added when that profile is enabled. vLLM, Redis, and the executor are not given public names.

Check it:

```bash
docker logs server-caddy
docker exec server-caddy caddy validate --config /etc/caddy/Caddyfile
```

---

# 15. Domain and Cloudflare

The records, token, and port forwards are created while you follow `repo_setup_guide.md`. This section is the policy those steps carry out.

Register a domain and host its DNS on Cloudflare.

https://www.cloudflare.com/

Create DNS records for the hostnames you are actually serving, aimed at the home public IP. Proxy the HTTP and HTTPS names (Cloudflare's orange-cloud proxy) so those sites get Cloudflare DNS plus edge protection.

Cloudflare does not hide the home IP for every protocol. Minecraft on `25565/tcp` is a separate forward and is not protected just because the web hostnames are proxied.

If the public IP changes, use Cloudflare Dynamic DNS and store that API token as a secret.

For certificates, use Caddy with the Cloudflare DNS challenge so certificates issue while the records are proxied:

https://github.com/caddy-dns/cloudflare

The Cloudflare API token used for DNS edits is a secret. It does not go in Git, the dashboard, or logs.

Confirm in a browser that each finished site loads over HTTPS and that plain HTTP redirects to HTTPS.

---

# 16. Forward Only the Public Ports

On OPNsense, forward to `192.168.50.10`:

```text
TCP 80    -> server
TCP 443   -> server
TCP 25565 -> server, only if Minecraft is public
```

Do not forward `22` or internal application ports (`3000`, `8000`, `8080`, database ports, `6379`, vLLM's port, or anything similar).

From outside the home network, `https://dashboard.example.com` should reach Caddy. SSH to the public IP should fail.

---

# 17. GitHub Pages Entry Point

The GitHub Pages site is the public entry. It links to the server and shows a maintenance message when the health check fails.

```text
GitHub Pages
     |
     | HTTPS health check
     v
Server /health
     |
     +---- Online  -> show the server link
     |
     +---- Offline -> show a maintenance page
```

Add a Caddy or dashboard route that returns only:

```json
{"status":"online"}
```

That endpoint must not return CPU, RAM, process lists, usernames, internal addresses, Docker details, or security logs.

Verify it from a phone that is not on Tailscale, then point the GitHub Pages site at that URL.

---

# 18. Install Authentik and Create Accounts

Authentik is the identity provider for people. `scripts/setup.sh` starts it from `docker-compose.yml` and loads `infrastructure/authentik/blueprints/server.yaml`, which turns off open enrollment.

https://goauthentik.io/

It is published only through Caddy, on `auth.example.com`. Port 9000 is not open on the host.

The bootstrap account is `akadmin`. Its password is `AUTHENTIK_BOOTSTRAP_PASSWORD` in `.env`. That account, plus any other administrators you create on the dashboard Admin page during setup, are the only accounts created without a referral code.

There is no shared server password. Each admin has their own account, for example:

```text
Spencer     Admin
```

Add every other founding admin the same way, now, while you are still in setup.

Create two roles and keep them separate:

- Administrator
- Regular user

## Referral codes for everyone else

After the initial admins exist, turn open self-registration off.

Every later account requires a referral code issued by an existing administrator. The person joining types that code during signup. The code has to link back to the admin account that created it.

Use the dashboard Admin page to issue codes. It creates an Authentik invitation and writes the sponsoring administrator into the dashboard database, because the Authentik API call itself is made with a service token. The dashboard row is the sponsorship log.

- Enrollment without a valid code fails.
- Only administrators can create codes.
- Each code is single-use, or has an explicit use cap.
- Unused codes can be revoked.
- The dashboard database stores the administrator who issued the code. Authentik's API call uses a service token, so the person who clicked the button is recorded on the dashboard row.
- When the code is used, that row remains after the code is consumed.

Each account-creation event records:

```text
New account
Referral code
Sponsoring administrator
Time
```

That is the log of who joined through which admin. Administrators can list the accounts created with their codes.

Regular users cannot issue codes and cannot create accounts for anyone else.

## What each role can do

Administrators can manage users, issue and revoke referral codes, see who used their codes, manage applications, deploy services, control LLMs, view security logs and detailed system information, configure infrastructure, and approve privileged actions.

Regular users can use the applications, LLMs, media, collaboration tools, Minecraft, and shared downloads they are allowed to use, and they can participate in server chat.

Regular users never receive:

- Docker
- SSH
- a server shell
- firewall configuration
- secrets
- infrastructure credentials
- unrestricted filesystem access
- administrator APIs
- unrestricted deployment credentials
- the ability to run arbitrary shell commands
- the ability to deploy privileged containers
- the ability to control the privileged executor

## Check before leaving this step

- Signing up with no code fails.
- Signing up with an administrator's code creates one account, and the event log shows that admin as the sponsor.
- A second use of a single-use code fails.
- A regular user has no way to create a code.
- Disabling one account does not change anyone else's password.
- A supported application signs in through Authentik instead of a separate local password.

Set session length in Authentik and let applications use that SSO session. Integrate each later service with Authentik as you install it. A service that cannot do SSO still needs its own per-person accounts, behind Caddy, with no shared password.

---

# 19. Deploy the Rest One Service at a Time

Install in this order. Verify the service before starting the next one.

```text
Caddy
  -> Authentik
  -> Dashboard
  -> Monitoring
  -> Logging
  -> LLM infrastructure
  -> Media
  -> Git
  -> Collaboration
  -> Minecraft
  -> Optional services
```

Caddy and Authentik are already in place by this point. Continue with the dashboard.

---

# 20. Unified Dashboard

The dashboard is the primary interface. Build it as its own Compose project and proxy it through Caddy.

Planned pages:

```text
Home
Services
LLMs
Websites
Minecraft
Media
Files
Git
Collaboration
Notifications
Chat
Processes
Logs
Admin
```

Requirements:

- Login goes through Authentik. The dashboard does not invent a second user database.
- The Admin page and every process control are limited to administrators.
- Every page can show a compact status bar: CPU, RAM, GPU, storage, and power.
- Realtime CPU, RAM, GPU, power, network, service state, active users, and chat use authenticated WebSockets.
- Redis holds transient realtime state and messages. Bind Redis to localhost or an internal Docker network. Do not write high-frequency samples straight to disk, and do not publish Redis publicly.
- Authenticated users can open a shared chat panel. Messages are tied to Authentik accounts and kept according to the retention policy you set.
- The Processes page is the server task manager. It lists processes with CPU, RAM, and GPU. Only administrators can act on them.
- The public health check from step 17 can live here, and it still returns only `{"status":"online"}`.

The browser never talks to the Docker socket. The dashboard backend is the place that checks the Authentik session and the role before it does anything.

---

# 21. Monitoring

Run Prometheus and Grafana in Docker, on localhost or the internal network, behind Authentik.

https://prometheus.io/

https://grafana.com/

Scrape host and container metrics so Grafana can show:

```text
CPU
RAM
GPU
GPU memory
Storage
Network
Power
Temperature
Docker containers
LLM requests
Active users
Failed logins
```

Alert, through Grafana and the notification step, on:

```text
Disk > 85%
Disk > 95%
RAM sustained > 90%
GPU memory exhaustion
Container crash loop
Repeated failed logins
Unexpected admin login
Server unreachable
Backup failure
LLM resource spike
```

Grafana is an admin tool. Regular users see the dashboard status bar, not the full metrics stack.

---

# 22. Logging

Run Grafana Loki for centralized, searchable logs.

https://grafana.com/oss/loki/

Ship application and audit logs to Loki. Administrators need to be able to search at least:

```text
User login
Failed login
Account creation (new account, referral code, sponsoring administrator, time)
Referral code issued
Referral code used
Referral code revoked
Account disabled
Application deployed
Application removed
Website added
Website removed
LLM started
LLM stopped
LLM request
Service restarted
Minecraft started
Server overload
Server shutdown
Configuration change
Admin action
```

Never write passwords, API keys, session tokens, cookies, or private keys into logs.

---

# 23. LLM Infrastructure

Treat models as untrusted software. Prompt injection does not make a model an administrator.

## vLLM

https://github.com/vllm-project/vllm

vLLM is the inference server. Follow its official Docker instructions and pass the GPU through with the NVIDIA Container Toolkit. Keep the API on localhost or an internal network. The dashboard or Open WebUI is the user-facing front, and that front signs in through Authentik.

Do not assume a fixed speedup over any other runtime. Performance depends on the GPU, model, quantization, context length, and concurrency.

## LLMLingua

https://github.com/microsoft/LLMLingua

LLMLingua compresses long prompts and histories before they reach vLLM. The compression ratio and the quality impact depend on the workload.

```text
User -> Frontend -> LLMLingua -> vLLM -> Local model
```

## Model roles

Keep a lightweight server-manager model and a general chat model available. Keep coding, reasoning, research, and other specialized models dormant until someone starts them. Dormant models should not hold significant GPU or RAM while they are stopped.

## What the front-end model may do

It may answer questions, read approved metrics, search the internet, format text, write ordinary code, and recommend another model.

It has:

```text
NO root access
NO unrestricted shell
NO Docker socket
NO arbitrary filesystem writes
NO arbitrary network administration
NO generic command execution
```

A question such as "how much RAM is being used?" calls a hardcoded read-only API, for example `GET /api/server/stats`. It does not open a shell.

## Privileged executor

Infrastructure changes go through a small non-AI executor:

1. Verify the authenticated administrator.
2. Verify the request and session.
3. Check an explicit action allowlist.
4. Validate parameters.
5. Run only a predefined script.
6. Log the action.

There is no `execute_shell(command)` endpoint. The model cannot generate its own administrator approval. If authentication, authorization, validation, or an internal dependency fails, the action does not run.

## Server-manager model

A lightweight model may run continuously to watch approved statistics, notice sustained load, notice crashed services, point at known temporary files, organize approved metadata, format documentation, recommend cleanup, recommend starting a dormant model, and summarize logs that were explicitly given to it.

It does not perform destructive or privileged actions on its own. It is not the administrator of the server. Authority stays with the human administrator, then Authentik, then the allowlisted executor.

## Kill switch

Label every AI container:

```text
ai-model=true
```

Emergency stop:

```bash
docker ps -q --filter "label=ai-model" | xargs -r docker stop
```

The switch has to be on the administrator dashboard and usable locally on the server. The dashboard control requires an administrator session. Every use is logged. It has to work when the models are down, because it is what stops them. Stopping AI containers leaves Caddy, the dashboard, files, and the firewall running.

Confirm the label filter stops a test model container and leaves Caddy up.

---

# 24. Media (Jellyfin)

https://jellyfin.org/

Run Jellyfin in Docker. Point libraries at `/srv/server/media`. Put it behind Caddy and Authentik.

Photos need an authenticated upload path. Do not publish Jellyfin's port except through Caddy on localhost.

---

# 25. Git (Forgejo)

https://forgejo.org/

Forgejo is the private Git server. Run it in Docker, behind Caddy and Authentik, with repositories stored under `/srv/server/data` so they are included in backups.

---

# 26. Collaboration (Nextcloud and Collabora)

https://nextcloud.com/

https://www.collaboraonline.com/

Run both in Docker behind Caddy and Authentik. They provide files, documents, spreadsheets, and browser editing. Role-based access comes from Authentik groups.

---

# 27. Minecraft

Run Minecraft as its own Compose project. Do not mount the host filesystem into it.

Public port, only if you want it public:

```text
25565/tcp
```

The dashboard shows online state, players, RAM, CPU, uptime, and version. Administrators can start, stop, restart, open the console, and take backups. Those controls go through the privileged executor, not through the model.

If you skip public Minecraft, remove the UFW rule and the port forward.

---

# 28. Application Deployment (Coolify)

https://coolify.io/

Coolify deploys from Git:

```text
GitHub
   |
   | Push
   v
Coolify
   |
   +-- Build
   +-- Create container
   +-- Configure network
   +-- Deploy
   |
   v
Caddy
   |
   v
app.example.com
```

Each app gets its own container and only the network access it needs. The dashboard reads Coolify's API and creates tiles with the application name, creator name, GitHub username, server account, repository, status, URL, and deployment time.

Creator identity comes from the authenticated deployment, not from a label the user typed.

Coolify's own admin UI stays behind Authentik, or on Tailscale if you are not ready to publish it.

---

# 29. Notifications (ntfy)

https://ntfy.sh/

Run ntfy in Docker. Use separate logical channels:

```text
Admin
- Login events
- High load
- Disk warnings
- LLM incidents
- Service failures
- Security events
- Shutdowns

General
- Maintenance
- Downtime
- Game nights
- Server announcements
```

Admin topics require authentication and an admin role. An unguessable topic name is not the access control.

Wire the Grafana alerts from step 21 to the admin channel.

---

# 30. Discord and Lavalink

Discord bots may run continuously for server status, notifications, application management, log summaries, voice commands, music, server information, and automation.

Store bot tokens as secrets. They never go into Git, logs, dashboard responses, or model prompts.

Lavalink is the self-hosted audio backend for a custom music bot:

https://github.com/lavalink-devs/Lavalink

```text
Discord -> custom bot -> Lavalink -> audio source
```

Keep Lavalink on the internal network.

---

# 31. Optional Services

Install these only when the core path above is healthy.

## Codegraph

https://github.com/colbymchenry/codegraph

Use it to index local repositories so development models can see files, classes, functions, references, dependencies, and structure without loading whole repos into context.

Do not index `.env` files, private keys, passwords, or API tokens.

## LanCache

https://lancache.net/

Optional only if you have disk to spare. The first download of supported game content comes from the internet and fills the cache. A later matching download can be served from the server.

Support depends on the game platform and its CDN. Give the cache a hard storage limit so it cannot fill the disk. It does not get a path into the home LAN that bypasses the VLAN deny rules. Clients on the home LAN reach it only if you add an explicit, limited firewall exception, and that exception is not a reason to open the rest of the server VLAN.

## Shared large files

`/srv/server/storage` holds installers, game files, and project releases. Put a quota on it and include it in the disk alerts.

---

# 32. Secrets

Never commit real credentials.

Do not commit:

```text
.env
*.key
*.pem
password files
API tokens
Discord tokens
SSH private keys
Cloudflare API tokens
database passwords
```

Commit examples as `.env.example` with blank values. Inject real values at runtime with environment variables, Docker secrets, or a secret manager.

---

# 33. Backups

Back up:

```text
Caddy configuration
Docker Compose files
Authentik data
Dashboard data
Forgejo repositories
Minecraft worlds
Important application data
User uploads
```

LLM weights and caches can be left out when you can download them again.

The copy under `/srv/server/backups` is staging. It is not the backup that survives a dead disk.

```text
Server
  |
  +-- Local backup
  +-- External backup
  +-- Optional off-site backup
```

Restore once onto a spare folder or a spare machine before you trust the job. A backup that has never been restored is unfinished. Alert on backup failure through ntfy.

---

# 34. Operations

```bash
# System
hostname
ip addr
df -h
free -h
uptime

# Docker
docker ps
docker images
docker compose ps
docker logs CONTAINER_NAME
docker restart CONTAINER_NAME

# Firewall
sudo ufw status verbose
sudo ufw status numbered

# Caddy
sudo systemctl status caddy
sudo systemctl reload caddy
sudo caddy validate --config /etc/caddy/Caddyfile

# Tailscale
tailscale status
tailscale ip -4

# Stop AI containers only
docker ps -q --filter "label=ai-model" | xargs -r docker stop

# Reboot
sudo reboot
```

---

# 35. If the Server Is Compromised

1. Disconnect it from the network.
2. Leave it offline. Do not clean it while it is still connected.
3. Preserve useful logs if you can.
4. Rotate credentials that may have been exposed.
5. Disable compromised accounts.
6. Reinstall Ubuntu.
7. Restore only known-good data and configuration.
8. Recreate containers from trusted Compose files and images.
9. Rotate API keys and service tokens.
10. Confirm the VLAN still cannot reach the home LAN, then reconnect the server.

Rebuilding should be inconvenient, not fatal. That is why Authentik, git, Minecraft, and uploads have an external copy.

---

# 36. Production Checklist

```text
[ ] Server is on an isolated VLAN
[ ] Server cannot initiate connections to the home LAN
[ ] Home LAN cannot access server admin interfaces by default
[ ] Tailscale works for administration
[ ] SSH is not publicly exposed
[ ] UFW is enabled
[ ] Only required public ports are forwarded
[ ] HTTPS is enabled
[ ] HTTP redirects to HTTPS
[ ] GitHub Pages checks /health and /health returns only status
[ ] Every user has an individual account
[ ] Initial admin accounts were created during setup
[ ] Later accounts require an admin referral code
[ ] Account creation logs the sponsoring administrator
[ ] Regular users cannot issue referral codes
[ ] Admin and regular-user roles are separated
[ ] Authentik protects supported applications
[ ] Docker socket is not mounted by the dashboard, media, git, or LLM containers
[ ] Only Caddy publishes 80/443, and Minecraft publishes 25565 only when enabled
[ ] LLM containers have no unrestricted host access
[ ] LLMs cannot execute arbitrary shell commands
[ ] LLMs cannot access root
[ ] LLMs cannot directly modify arbitrary server files
[ ] Privileged actions require explicit authorization
[ ] Privileged actions use an allowlist
[ ] LLM emergency kill switch works
[ ] Secrets are not committed to Git
[ ] Logs do not contain credentials
[ ] Backups exist outside the server
[ ] Restore procedure has been tested
[ ] Resource limits exist for untrusted/public services
[ ] Monitoring and notifications are working
```

---

# 37. Order of Work

```text
 1. Install Ubuntu Server 24.04 LTS on the NVMe. Leave the bay SSD empty.
 2. Find the bad DIMM slot, leave it empty, and confirm the remaining RAM.
 3. SSH from your PC and reserve the current address
 4. Update Ubuntu
 5. Install Tailscale and verify SSH from a second network
 6. Configure UFW
 7. Create the server VLAN and move the reservation to 192.168.50.10
 8. Prove the server cannot reach the home LAN
 9. Install Docker, confirm hello-world, and install the Titan driver if nvidia-smi will be used
10. Stop. Follow repo_setup_guide.md
```

The milestone for this file is:

```text
Ubuntu + Tailscale + UFW + server VLAN + Docker
```

Caddy, Authentik, the dashboard, and public HTTPS are the next file.
