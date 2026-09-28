# The Server

https://github.com/spencerboggs/home-server.git

A self-hosted, internet-accessible server for local AI, websites, games, private collaboration, media, development tools, and shared services.

The design has two primary goals:

1. Make the server feel like a private cloud with one unified frontend.
2. Treat the server as an isolated, potentially hostile machine so a compromise does not become a compromise of the rest of the home network.

---

## Architecture

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
             +------+------+              +------+------+ 
                    |                             |
                    |                    +--------+--------+
                    |                    |        |        |
                    |                    v        v        v
                    |                 Server   Services  Chat
                    |                 Stats
                    |                    |
                    |              +-----+------+
                    |              |            |
                    |              v            v
                    |           Processes     Hardware
                    |
                    +-----------------------------+
                                                  |
                         +------------------------+------------------------+
                         |                        |                        |
                         v                        v                        v
                  +-------------+          +-------------+          +-------------+
                  |    Docker   |          | Monitoring  |          |   Storage   |
                  |   Services  |          |   Grafana   |          | Media/Files |
                  +------+------+          |    Loki     |          +-------------+
                         |                 +-------------+
              +----------+----------+
              |          |          |
              v          v          v
            LLMs     Websites   Minecraft
              |
          +---+------+
          |          |
          v          v
        vLLM     LLMLingua
```

Network architecture:

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
                         |                 |
                         |  UFW            |
                         |  Docker         |
                         |  Caddy          |
                         |  Applications   |
                         +--------+--------+
                                  |
                         Internet: ALLOWED
                                  |
                         Home LAN: BLOCKED
                                  X
                                  |
                    +-------------+-------------+
                    |                           |
                 PCs/Phones                Other Devices
                 Home LAN                   Home LAN

                             ADMIN ACCESS
                                  |
                              Tailscale
                                  |
                                  v
                             Ubuntu Server
```

The server VLAN should have Internet access but should not be able to initiate connections to the normal home LAN.

---

# Technology Stack

| Area | Technology | Purpose |
|---|---|---|
| OS | Ubuntu Server 24.04 LTS | Base operating system |
| LAN IP | DHCP reservation / static LAN address | Stable internal address |
| Private administration | Tailscale | Remote administration without exposing SSH publicly |
| Host firewall | UFW | Additional host-level firewall |
| Network isolation | OPNsense + isolated VLAN | Prevents server-to-LAN access |
| Containers | Docker + Docker Compose | Application isolation and deployment |
| Reverse proxy | Caddy | HTTPS and routing to internal services |
| Public DNS | Cloudflare | DNS and optional HTTP/HTTPS proxying |
| TLS | HTTPS / Let's Encrypt | Encrypted web traffic |
| Identity | Authentik | SSO, users, roles, and session control |
| Deployment | Coolify | Git-based application deployment |
| Git | Forgejo | Private repositories |
| LLM serving | vLLM | High-throughput local inference |
| Prompt compression | LLMLingua | Compresses long prompts and histories |
| LLM UI | Open WebUI or custom frontend | User-facing AI interface |
| Metrics | Prometheus + Grafana | System and application monitoring |
| Logs | Grafana Loki | Centralized searchable logs |
| Real-time state | Redis | Temporary state, queues, and realtime features |
| Notifications | ntfy | Admin and user notifications |
| Media | Jellyfin | Private media streaming |
| Collaboration | Nextcloud + Collabora | Private documents and spreadsheets |
| Game cache | LanCache, optional | Local cache for supported game downloads |
| Discord audio | Lavalink | Self-hosted Discord audio backend |
| Code indexing | Codegraph, optional | Repository/code structure indexing |

The exact service list can change. Services should remain containerized, authenticated, isolated, and documented.

---

# Security Model

Security is a primary design requirement.

The server is intentionally treated as a machine that could eventually be compromised. The desired failure mode is:

> If the server is compromised, the attacker gets the server, not the rest of the home network.

## Network Isolation

The server belongs on its own VLAN.

Example:

```text
Home LAN
192.168.1.0/24
    |
    | BLOCKED
    |
Server VLAN
192.168.50.0/24
    |
    +---- Server
```

Firewall policy:

```text
Server VLAN -> Internet       ALLOW
Server VLAN -> Home LAN       DENY
Server VLAN -> Other VLANs    DENY
Home LAN -> Server VLAN       DENY by default
Management -> Server VLAN     ALLOW where required
```

Recommended firewall: OPNsense or equivalent VLAN-capable firewall.

This boundary is more important than relying on the Ubuntu firewall alone. The server should not be able to scan, SSH into, access SMB shares on, or otherwise initiate connections to normal home devices.

## Host Firewall

UFW adds another layer on Ubuntu.

Typical rules:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow in on tailscale0 to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 25565/tcp

sudo ufw enable
```

Remove the Minecraft rule if Minecraft is not public.

Verify:

```bash
sudo ufw status verbose
```

Docker services should not be published on the host unless necessary. This repository publishes only Caddy on 80/443 and, when enabled, Minecraft on 25565. Other containers are reached on the Docker network. Caddy proxies to names such as `server-dashboard:8000`.

Anything you run outside that Compose file should bind to localhost instead of every interface:

```yaml
ports:
  - "127.0.0.1:8080:8080"
```

instead of:

```yaml
ports:
  - "8080:8080"
```

## Public Ports

Normally only these ports are forwarded from the router:

```text
80/tcp       HTTP
443/tcp      HTTPS
25565/tcp    Minecraft, if enabled
```

Do not expose SSH, Docker, databases, Ollama/vLLM APIs, Redis, or internal admin panels directly to the Internet.

---

# HTTPS and Reverse Proxy

Caddy is the public entry point for web applications.

```text
dashboard.example.com
        |
        v
      Caddy
        |
        v
server-dashboard:8000
```

Example from this repository:

```text
dashboard.example.com {
    reverse_proxy server-dashboard:8000
}
```

Caddy can automatically obtain and renew HTTPS certificates for a real domain.

HTTP should redirect to HTTPS. Passwords, sessions, and application data should never be sent over plain HTTP.

## Cloudflare

A domain should eventually replace the raw public IP as the normal entry point.

Example:

```text
dashboard.example.com
media.example.com
git.example.com
apps.example.com
```

Cloudflare provides DNS and can proxy supported HTTP/HTTPS traffic. It can also provide additional edge security and DDoS protection.

Cloudflare proxying does not hide the home IP for every protocol. A separately exposed Minecraft port is not automatically protected just because the domain uses Cloudflare.

---

# GitHub Pages Entry Point

The GitHub Pages site is the public entry. It links to the server and shows a maintenance message when the health check fails.

```text
GitHub Pages
     |
     | HTTPS health check
     v
Server /health
     |
     +---- Online -> Show server link
     |
     +---- Offline -> Show maintenance UI
```

The public health endpoint should expose minimal information such as:

```json
{"status":"online"}
```

Do not expose CPU, RAM, process lists, usernames, internal addresses, Docker information, or security logs through a public health endpoint.

---

# Authentication and Accounts

There is no global server password.

Every person gets an individual account:

```text
Spencer     Admin
Alice       User
Bob         User
```

Authentik is the central identity provider. Applications should use OAuth2/OIDC/SSO where supported.

An administrator can disable one account without changing anyone else's password. Each account is the identity in the audit log.

## How accounts are created

Initial administrator accounts are created while the server is being set up. Those are the only accounts created without a referral.

After that, open self-registration stays off. Anyone else who wants an account must be referred by an existing administrator. They enter a referral code that is tied to that administrator's account. The code is how the server knows which admin sponsored the signup.

When the account is created, record:

```text
New account
Referral code
Sponsoring administrator
Time
```

That record is the log of who joined through which admin. Administrators can issue codes, revoke unused codes, and see which accounts were created with their codes. A code should be single-use, or explicitly capped, so it cannot be shared indefinitely without a new approval.

Regular users cannot issue referral codes and cannot create accounts for other people.

Regular users should never receive access to:

- Docker
- SSH
- server shell
- firewall configuration
- secrets
- infrastructure credentials
- unrestricted filesystem access
- administrator APIs
- unrestricted deployment credentials

---

# LLM Security

LLMs are treated as untrusted software. Prompt injection, jailbreaks, malicious users, and model mistakes must not turn an LLM into an unrestricted server administrator.

The user-facing LLM has:

```text
NO root access
NO unrestricted shell
NO Docker socket
NO arbitrary filesystem writes
NO arbitrary network administration
NO generic command execution
```

A request such as:

> How much RAM is being used?

should call a hardcoded read-only API such as:

```text
GET /api/server/stats
```

The model does not receive a shell.

## Dual-Agent Architecture

```text
                 User
                   |
                   v
          Front-End LLM
                   |
          Read-only tools
                   |
            Safe Server API
                   |
                   v
              Server data

Admin-approved change
                   |
                   v
       Authenticated admin request
                   |
                   v
       Non-AI Executor Service
                   |
          Explicit allowlist
                   |
                   v
       Pre-approved scripts
```

The front-end LLM can answer questions, read approved metrics, search the Internet, format text, write ordinary code, and recommend another model.

It cannot directly modify the server.

Privileged changes go through a small deterministic executor that:

1. Verifies the authenticated administrator.
2. Verifies the request/session.
3. Checks an explicit action allowlist.
4. Validates parameters.
5. Executes only a predefined script.
6. Logs the action.

There should be no generic `execute_shell(command)` endpoint.

The LLM must not be able to generate its own fake administrator approval.

---

# Server Manager LLM

A lightweight model may run continuously as the onboard server manager.

It can:

- Monitor approved resource statistics
- Detect sustained high load
- Detect stopped or crashing services
- Identify known temporary files
- Organize approved application metadata
- Format documentation
- Recommend cleanup
- Recommend when a dormant LLM should be started
- Summarize logs that have been explicitly made available to it

It should not independently perform destructive or privileged actions. Administrator approval is required for infrastructure changes.

---

# LLM Kill Switch

All AI containers should use a common Docker label:

```text
ai-model=true
```

Emergency shutdown:

```bash
docker ps -q --filter "label=ai-model" | xargs -r docker stop
```

This stops the AI containers while leaving the core server, files, dashboard, firewall, and other services running.

The kill switch should be:

- Available from the administrator dashboard
- Available locally on the server
- Protected by administrator authentication when exposed through the dashboard
- Logged
- Usable without an LLM

---

# LLM Infrastructure

## vLLM

https://github.com/vllm-project/vllm

vLLM is the primary high-throughput inference layer where the hardware and model are supported. It uses optimized inference and memory management for concurrent workloads.

Performance depends on the GPU, model, quantization, context length, and concurrency. A fixed speed multiplier over Ollama should not be assumed.

## LLMLingua

https://github.com/microsoft/LLMLingua

LLMLingua can compress long prompts and conversation history before inference. This can reduce context size and inference cost for workloads with large repeated histories.

The actual compression ratio and quality impact depend on the workload.

Architecture:

```text
User
  |
  v
Frontend
  |
  v
LLMLingua
  |
  v
vLLM
  |
  v
Local Model
```

## Model Roles

```text
Always Running
    |
    +-- Lightweight Server Manager
    +-- General Chat Model

Dormant
    |
    +-- Coding Model
    +-- Reasoning Model
    +-- Research Model
    +-- Specialized Models
```

Dormant models should only consume significant resources when activated.

---

# Unified Dashboard

The dashboard is the primary interface for the server.

Dashboard pages (all of these routes exist in the app):

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

Every page can optionally show a compact status bar:

```text
CPU 23% | RAM 48% | GPU 37% | Storage 62% | Power 184 W
```

The dashboard should use authenticated WebSockets for realtime information such as CPU, RAM, GPU, power, network, service state, active users, and chat.

Redis holds transient realtime state and chat fan-out. High-frequency samples stay off the disk.

---

# Task Manager

The Processes page acts like a server version of Windows Task Manager.

```text
Process             CPU     RAM      GPU
------------------------------------------------
vLLM                32%     18 GB    74%
Minecraft            8%      6 GB     0%
Caddy                1%      40 MB    0%
Dashboard            2%     120 MB    0%
Jellyfin             3%      1 GB    12%
```

Administrative process controls are restricted to administrators.

---

# Server Chat

Authenticated users can optionally access a shared chat panel on every page.

Messages are associated with server accounts and can be retained according to the server's configured policy.

---

# Audit Logging

Administrators need a centralized searchable event history.

Useful events include:

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

Grafana Loki can provide centralized log storage and search.

Never put passwords, API keys, session tokens, cookies, or private keys into logs.

---

# Notifications

ntfy can provide server notifications.

https://ntfy.sh/

Recommended logical channels:

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

Sensitive administrative alerts require authentication and an access control list.

---

# Collaboration

## Forgejo

https://forgejo.org/

Private Git repositories and a lightweight GitHub-like interface.

## Nextcloud + Collabora

https://nextcloud.com/

https://www.collaboraonline.com/

Private files, documents, spreadsheets, and browser-based collaboration.

These services should be protected by authentication and role-based access.

---

# GitHub Application Deployment

Coolify can handle Git-based application deployment.

https://coolify.io/

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

Each application should receive an isolated container and only the network permissions it requires.

The dashboard can query Coolify's API and automatically create application tiles containing:

```text
Application
Creator name
GitHub username
Server account
Repository
Status
URL
Deployment time
```

Creator identity should come from authenticated deployment metadata, not arbitrary user-provided labels.

---

# Code Indexing

Codegraph may be evaluated for indexing local repositories:

https://github.com/colbymchenry/codegraph

The goal is to help development LLMs understand files, classes, functions, references, dependencies, and project structure without repeatedly loading entire repositories.

Do not index secrets such as `.env` files, private keys, passwords, or API tokens unless there is a specific protected reason to do so.

---

# Media

Jellyfin can provide private media streaming.

https://jellyfin.org/

Example:

```text
/media
├── Movies
├── TV
├── Music
├── Photos
└── Other
```

Photos should have an authenticated upload interface.

Raw SMB/NFS shares should never be exposed to the public Internet.

---

# Game Update Cache

Optional feature if storage capacity allows it.

LanCache:

https://lancache.net/

Potential workflow:

```text
Friend A -> Internet -> LanCache -> Local storage
Friend B -> LanCache -> Local network
```

The first download consumes the Internet bandwidth. Matching later downloads may be served locally.

Actual support depends on the game platform and content delivery system. Do not assume every Steam, Epic, Xbox, or other download is cacheable.

The cache must have a storage limit so it cannot consume the entire server disk.

---

# Minecraft

Minecraft runs in an isolated Docker service.

Public port:

```text
25565/tcp
```

The dashboard can show:

```text
Online
Players
RAM
CPU
Uptime
Version
```

Administrators can receive:

```text
Start
Stop
Restart
Console
Backup
```

Minecraft should not have unrestricted access to the host filesystem.

---

# Discord

Discord bots can run continuously on the server for:

- Server status
- Notifications
- Application management
- Log summaries
- Voice commands
- Music
- Server information
- Automation

Bot tokens must be stored as secrets and never committed to Git, logs, dashboard responses, or LLM prompts.

## Lavalink

https://github.com/lavalink-devs/Lavalink

Lavalink can provide a self-hosted audio backend for custom Discord music bots.

```text
Discord
   |
Custom Bot
   |
Lavalink
   |
Audio Source
```

---

# Large File and Game Storage

Optional shared storage can contain frequently used large files, games, installers, and project releases.

Example:

```text
/downloads
/games
/software
/projects
/releases
```

Storage quotas and monitoring are required because the server has finite capacity.

---

# User Roles

## Administrator

Can:

- Manage users
- Issue and revoke referral codes
- See which accounts were created with their codes
- Manage applications
- Deploy services
- Control LLMs
- View security logs
- View detailed system information
- Configure infrastructure
- Approve privileged actions

## Regular User

Can:

- Use approved applications
- Use allowed LLMs
- Access media
- Access collaboration tools
- Use Minecraft
- Use shared downloads
- Participate in server chat

Regular users cannot:

- Execute arbitrary shell commands
- Access Docker
- Change firewall rules
- Read secrets
- Modify arbitrary server files
- Deploy privileged containers
- Control the privileged executor

---

# Repository

This git repository is what you clone onto the server after Ubuntu, Tailscale, UFW, the VLAN, and Docker are in place. The server has no desktop. People use the dashboard in a browser. Administrators use SSH over Tailscale.

Open-source services (Authentik, Caddy, Forgejo, Jellyfin, Nextcloud, Grafana, and the rest) are Docker images. `scripts/prefetch.sh` downloads them. They are not vendored into git. The full package and image list is in `repo_setup_guide.md`. The dashboard, executor, referral log, Caddyfile, and Compose files are the parts this repo owns.

```bash
git clone https://github.com/spencerboggs/home-server.git /srv/server/apps/the-server
cd /srv/server/apps/the-server
sudo bash scripts/setup.sh --format-bulk
```

Follow `server_setup_guide.md` through Docker, then follow `repo_setup_guide.md` from the start. That second guide is the clone, the disk pool, DNS, certificates, accounts, and the check that a browser off your home network can open the dashboard.

Disk layout:

```text
NVMe (PCIe adapter, Ubuntu is installed here)
├── /var/lib/docker
└── /srv/server/data     databases, Authentik, Forgejo, dashboard

Bay SSD, plus later disks, pooled with mergerfs
└── /srv/bulk            media, models, worlds, Nextcloud files, shared storage
```

New files go to the disk with the most free space. Adding a disk does not change the paths applications use.

---

# Installation

The installation is intentionally staged. Do not deploy everything at once.

## 1. Install Ubuntu Server

Download Ubuntu Server 24.04 LTS:

https://ubuntu.com/download/server

Install OpenSSH Server during setup.

Install Ubuntu on the NVMe in the PCIe slot. Leave the drive-bay SSD empty so `scripts/setup.sh --format-bulk` can claim it.

Create a normal Linux administrative account with a strong unique password.

## 2. Reserve the LAN IP

Create a DHCP reservation in the router based on the server's MAC address.

Example:

```text
Server: 192.168.50.10
```

A router-level reservation is preferred for the initial setup because it is simple to recover.

## 3. Update Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
```

## 4. Install Tailscale

https://tailscale.com/docs/install/linux

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Verify:

```bash
tailscale status
tailscale ip -4
```

Install Tailscale on every administrator's computer, on whatever network they use, and sign into the same tailnet:

https://tailscale.com/download

Verify SSH through Tailscale before you rely on it. Do not forward port 22 on the router. After this repository is on the server, give each additional programmer their own Linux user:

```bash
sudo bash scripts/admin/add-ssh-key.sh alice "ssh-ed25519 AAAA... alice@laptop"
```

## 5. Configure UFW

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow in on tailscale0 to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 25565/tcp
sudo ufw enable
```

Remove the Minecraft rule if it will not be public.

## 6. Configure the Server VLAN

Create a dedicated server VLAN on the router or OPNsense.

Example:

```text
Home LAN:    192.168.1.0/24
Server VLAN: 192.168.50.0/24
```

Firewall policy:

```text
Server VLAN -> WAN           ALLOW
Server VLAN -> Home LAN      DENY
Server VLAN -> Other VLANs   DENY
Home LAN -> Server VLAN      DENY by default
Admin -> Server VLAN         ALLOW as required
```

Test this before deploying public applications.

## 7. Install Docker

https://docs.docker.com/engine/install/ubuntu/

Install Docker Engine, CLI, containerd, Buildx, and Compose using Docker's official Ubuntu instructions.

Then:

```bash
sudo usermod -aG docker $USER
```

Log out and back in, then verify:

```bash
docker run hello-world
docker compose version
```

## 8. Clone this repository

```bash
git clone https://github.com/spencerboggs/home-server.git /srv/server/apps/the-server
cd /srv/server/apps/the-server
sudo bash scripts/setup.sh --format-bulk
```

That formats the empty bay SSD, creates `/srv/server/data` on the NVMe and `/srv/bulk` on the pool, writes `.env`, and starts the core stack: Caddy, Authentik, the dashboard, Redis, Prometheus, Grafana, Loki, and ntfy.

Edit `.env` with the real domain and Cloudflare token, then:

```bash
sudo bash scripts/up.sh core
```

## 9. Enable the remaining profiles

One at a time, after the previous one is healthy:

```bash
sudo bash scripts/up.sh media
sudo bash scripts/up.sh git
sudo bash scripts/up.sh collab
sudo bash scripts/up.sh games
sudo bash scripts/up.sh ai
sudo bash scripts/up.sh discord
sudo bash scripts/up.sh deploy
```

`games` requires `MINECRAFT_EULA=TRUE`. `ai` requires `VLLM_MODEL` and a working NVIDIA driver. `discord` requires `DISCORD_TOKEN`.

Sign in as `akadmin`. Create other founding administrators on the Admin page. Later accounts require a referral code from an administrator.

## 10. Configure the Domain

Register a domain and configure DNS through Cloudflare.

Example:

```text
dashboard.example.com
media.example.com
git.example.com
apps.example.com
```

## 11. Configure Router Port Forwarding

Forward only:

```text
TCP 80    -> server
TCP 443   -> server
TCP 25565 -> server, if required
```

Do not forward SSH or internal application ports.

## 12. Accounts

`scripts/setup.sh` starts Authentik and loads the blueprint that requires an invitation for enrollment.

The bootstrap administrator is `akadmin`. The password is `AUTHENTIK_BOOTSTRAP_PASSWORD` in `.env`. Create any other founding administrators from the dashboard Admin page during setup. Those are the only accounts created without a referral.

Then:

- Open self-registration stays off.
- Every later account requires an administrator referral code.
- The dashboard logs the new account, the code, the sponsoring administrator, and the time.
- Regular users cannot issue referral codes.
- Applications use OIDC/OAuth2 where supported.

## 13. Deploy Core Services

The core profile is already up after setup. Enable later profiles from step 9, and verify each one before the next.

---

# Operations

Useful commands:

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
docker logs server-caddy
docker exec server-caddy caddy validate --config /etc/caddy/Caddyfile
sudo bash scripts/up.sh core

# Stop AI containers only
sudo bash scripts/emergency/llm-kill.sh

# Tailscale
tailscale status
tailscale ip -4

# Reboot
sudo reboot
```

---

# Secrets

Never commit real credentials to Git.

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

Provide examples through files such as:

```text
.env.example
```

Secrets should be injected at runtime through environment variables, Docker secrets, or a dedicated secret manager as the infrastructure matures.

---

# Backups

Back up at least:

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

The server's own disk must not be the only backup.

Recommended:

```text
Server
  |
  +-- Local backup
  +-- External backup
  +-- Optional off-site backup
```

Rebuildable LLM model files and caches can generally be excluded if they can be downloaded again.

---

# Monitoring and Alerts

Monitor:

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

Useful alerts:

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

---

# Repository Structure

```text
the-server/
├── README.md
├── server_setup_guide.md
├── repo_setup_guide.md
├── docker-compose.yml
├── .env.example
├── github-pages/
├── infrastructure/
│   ├── caddy/
│   ├── authentik/
│   ├── monitoring/
│   └── ntfy/
├── dashboard/
│   ├── frontend/
│   └── backend/
├── services/
│   ├── executor/
│   ├── llmlingua/
│   └── discord/
├── scripts/
│   ├── setup.sh
│   ├── prefetch.sh
│   ├── up.sh
│   ├── check.sh
│   ├── admin/
│   ├── storage/
│   ├── backup/
│   ├── health/
│   ├── maintenance/
│   └── emergency/
└── config/
```

---

# Development Principles

### Least privilege

Every service receives only the access it actually needs.

### Network isolation

A compromised public service must not be able to reach the home LAN.

### Individual authentication

Every person uses their own account.

### Referral-based signup

Initial administrator accounts are created during setup. Every later account requires an administrator's referral code, and that sponsorship is logged.

### No generic shell tools for LLMs

Models never receive unrestricted command execution.

### Explicit allowlisting

Privileged automation can perform only predefined actions.

### Fail closed

If authentication, authorization, validation, or an internal dependency fails, the action should not occur.

### Auditability

Security-sensitive actions should be logged with the responsible account.

### Backups

Important data must survive a server failure or rebuild.

### Resource limits

Public and untrusted services should have sensible CPU, RAM, GPU, and storage limits where practical.

---

# Recovery

If the server is compromised:

1. Disconnect it from the network.
2. Do not attempt to clean a compromised machine while it remains online.
3. Preserve useful logs if possible.
4. Rotate credentials that may have been exposed.
5. Disable compromised accounts.
6. Reinstall the operating system.
7. Restore only known-good data and configuration.
8. Recreate containers from trusted configuration and images.
9. Rotate API keys and service tokens.
10. Verify VLAN and firewall isolation before reconnecting the server.

The infrastructure should make a server rebuild inconvenient, not catastrophic.

---

# Roadmap

## Phase 1: Foundation

- [ ] Ubuntu Server
- [ ] DHCP reservation
- [ ] Tailscale
- [ ] UFW
- [ ] Server VLAN
- [ ] OPNsense/firewall isolation
- [ ] Docker
- [ ] Backups

## Phase 2: Internet Access

- [ ] Domain
- [ ] Cloudflare DNS
- [ ] Router port forwarding
- [ ] Caddy
- [ ] HTTPS
- [ ] GitHub Pages status/entry page

## Phase 3: Identity

- [ ] Authentik
- [ ] Initial admin accounts created at setup
- [ ] Admin referral codes required for every later account
- [ ] Account-creation log tied to the sponsoring admin
- [ ] Regular user accounts
- [ ] OIDC/OAuth2 integrations
- [ ] Session management

## Phase 4: Dashboard

- [ ] Unified frontend
- [ ] Login
- [ ] Server statistics
- [ ] Process monitor
- [ ] Service status
- [ ] Realtime WebSocket data
- [ ] Global chat
- [ ] Application directory

## Phase 5: AI

- [ ] vLLM
- [ ] LLMLingua
- [ ] General-purpose LLM
- [ ] Dormant development LLMs
- [ ] Server manager LLM
- [ ] Read-only server APIs
- [ ] Privileged executor
- [ ] LLM kill switch
- [ ] LLM usage logging

## Phase 6: Applications

- [ ] Minecraft
- [ ] Jellyfin
- [ ] Forgejo
- [ ] Nextcloud
- [ ] Collabora
- [ ] Coolify
- [ ] Discord bots
- [ ] Lavalink
- [ ] ntfy

## Phase 7: Advanced

- [ ] Grafana
- [ ] Loki
- [ ] Prometheus
- [ ] Redis
- [ ] Codegraph
- [ ] LanCache
- [ ] Local file/game repository
- [ ] Automated application discovery
- [ ] Advanced backup system
- [ ] Resource quotas

---

# Production Security Checklist

```text
[ ] Server is on an isolated VLAN
[ ] Server cannot initiate connections to the home LAN
[ ] Home LAN cannot access server admin interfaces by default
[ ] Tailscale works for administration
[ ] SSH is not publicly exposed unnecessarily
[ ] UFW is enabled
[ ] Only required public ports are forwarded
[ ] HTTPS is enabled
[ ] Every user has an individual account
[ ] Initial admin accounts were created during setup
[ ] Later accounts require an admin referral code
[ ] Account creation logs the sponsoring administrator
[ ] Regular users cannot issue referral codes
[ ] Admin and regular-user roles are separated
[ ] Authentik protects supported applications
[ ] Docker socket is not exposed to public applications
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

# Core Security Boundary

The server manager LLM is **not** the administrator of the server.

It is an AI assistant operating inside a constrained system.

The actual authority remains:

```text
Administrator
      |
      v
Authentication
      |
      v
Authorization
      |
      v
Deterministic Executor
      |
      v
Allowlisted Action
```

The LLM can recommend an action, but it cannot bypass authentication or authorization by convincing itself, another model, or a user that an action is safe.

---

# Useful Links

- Ubuntu Server: https://ubuntu.com/download/server
- Docker: https://docs.docker.com/
- Caddy: https://caddyserver.com/
- Tailscale: https://tailscale.com/
- OPNsense: https://opnsense.org/
- Cloudflare: https://www.cloudflare.com/
- Authentik: https://goauthentik.io/
- vLLM: https://github.com/vllm-project/vllm
- LLMLingua: https://github.com/microsoft/LLMLingua
- Coolify: https://coolify.io/
- Forgejo: https://forgejo.org/
- Nextcloud: https://nextcloud.com/
- Collabora: https://www.collaboraonline.com/
- Jellyfin: https://jellyfin.org/
- LanCache: https://lancache.net/
- Lavalink: https://github.com/lavalink-devs/Lavalink
- Codegraph: https://github.com/colbymchenry/codegraph
- ntfy: https://ntfy.sh/
