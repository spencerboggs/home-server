# Repository Setup Guide

https://github.com/spencerboggs/home-server.git

Follow this after `server_setup_guide.md` sections 0 through 11. Docker's hello-world container has already run. Tailscale SSH works. UFW is on. The server is on `192.168.50.10` and cannot reach the home LAN.

This guide puts the repository on that machine, starts the services, and checks that a browser anywhere on the internet can open the dashboard.

Administrators, managers, and programmers are expected to be on other networks. They reach SSH through Tailscale. Port 22 is never forwarded on the router. Regular users stay on the website and do not join the tailnet.

Do the steps in order. If a command fails, stop and fix that step before the next one. The first public milestone is the core profile: Caddy, Authentik, the dashboard, monitoring, logs, and ntfy. Add the other profiles after that milestone passes the phone check.

The server is an HP Z820. The bad memory slot is already empty, Ubuntu is on the NVMe, and the bay SSD is still blank. The Titan driver is installed only if `nvidia-smi` shows the card. A Kepler Titan (GTX Titan, Titan Black, Titan Z) does not run the vLLM image. Skip the ai profile on that card. The rest of the stack does not use the GPU.

The server has no desktop. Administration is an SSH session over Tailscale, from whatever network that person is on. Everyone else uses a browser and their own account. A later NAS is not part of this guide.

---

# 0. What must already be true

From your own PC, SSH over Tailscale and confirm:

```bash
tailscale ip -4
ip -4 addr show
docker run hello-world
sudo ufw status verbose
free -h
lsblk
nvidia-smi || true
ping -c 1 -W 2 192.168.1.1 || echo "home LAN is blocked"
```

Confirm:

- A Tailscale address, and SSH to it succeeds
- `192.168.50.10` on the server
- `docker run hello-world` prints a success message
- UFW active, with 22 allowed on `tailscale0` only, plus 80, 443, and 25565
- The ping to `192.168.1.1` fails
- `free -h` shows the RAM left after the bad Z820 slot was emptied (about 112 GB if you removed a 16 GB stick, or about 120 GB if you removed an 8 GB stick)
- The bay SSD is still empty. `lsblk` shows Ubuntu on `nvme0n1` and no filesystem yet on the other disk
- `nvidia-smi` prints the Titan if you will run the ai profile. Skip that check when the card is a Kepler Titan and the ai profile will stay off

If any of those are wrong, go back to `server_setup_guide.md`. Do not start this guide on a server that can still reach the home LAN, or on a server that is still using the bad memory slot.

---

# 1. Put the repository on the server

Install git on the server:

```bash
sudo apt update
sudo apt install -y git
```

## If the project is already on GitHub

```bash
sudo mkdir -p /srv/server/apps
sudo chown "$USER:$USER" /srv/server/apps
git clone https://github.com/spencerboggs/home-server.git /srv/server/apps/the-server
cd /srv/server/apps/the-server
```

## If the project is only on your Windows PC

From PowerShell, using the Tailscale address of the server:

```powershell
scp -r "D:\Programs\Current Projects\the-server" spencer@100.100.100.20:/tmp/the-server
```

Use your Linux username and the address from `tailscale ip -4`. Then on the server:

```bash
sudo mkdir -p /srv/server/apps
sudo rm -rf /srv/server/apps/the-server
sudo mv /tmp/the-server /srv/server/apps/the-server
sudo chown -R "$USER:$USER" /srv/server/apps/the-server
cd /srv/server/apps/the-server
```

Stay in `/srv/server/apps/the-server` for the rest of this guide.

---

# 2. Download packages and images

Ubuntu Server already has the base system from `server_setup_guide.md`. This step installs the extra packages this repository uses and pulls every container image. Run it from the repository directory. It needs Docker, which section 11 of the server guide already installed.

Core only (dashboard, Authentik, Caddy, monitoring, ntfy):

```bash
sudo bash scripts/prefetch.sh core
```

Every profile, including the large AI images:

```bash
sudo bash scripts/prefetch.sh all
```

One or more profiles:

```bash
sudo bash scripts/prefetch.sh core media git collab
```

`scripts/setup.sh` and `scripts/up.sh` pull anything still missing, and they build the dashboard, Caddy, executor, LLMLingua, and Discord images. Prefetch is the explicit download list so you can see the traffic before the first start. The AI profile downloads several gigabytes. Skip `all` until you intend to run that profile.

## Ubuntu packages

`scripts/prefetch.sh` installs these with apt:

```bash
sudo apt-get update
sudo apt-get install -y git python3 mergerfs ca-certificates curl parted e2fsprogs
```

| Package | Why it is here |
|---|---|
| git | Clone and later `git pull` |
| python3 | `scripts/generate_env.py` and `scripts/render_runtime.py` |
| mergerfs | Pool the bay SSDs at `/srv/bulk` |
| ca-certificates | HTTPS downloads |
| curl | Health checks and the Tailscale installer from the server guide |
| parted | Partition the empty bay SSD when you pass `--format-bulk` |
| e2fsprogs | `mkfs.ext4` for that disk |

`lsblk` and `mount` come with Ubuntu. The `mergerfs` package pulls in FUSE. Docker, UFW, and Tailscale were installed by `server_setup_guide.md` and are not installed again here.

## Container images by profile

These are the `docker pull` lines. `scripts/prefetch.sh` runs the ones for the profiles you name.

Core:

```bash
docker pull postgres:16-alpine
docker pull ghcr.io/goauthentik/server:2026.8.3
docker pull redis:7-alpine
docker pull prom/prometheus:v3.4.0
docker pull grafana/grafana:11.6.0
docker pull grafana/loki:3.4.2
docker pull grafana/promtail:3.4.2
docker pull prom/node-exporter:v1.9.1
docker pull gcr.io/cadvisor/cadvisor:v0.49.1
docker pull binwiederhier/ntfy:v2.14.0
docker pull caddy:2-builder-alpine
docker pull caddy:2-alpine
docker pull node:22-alpine
docker pull python:3.12-slim
```

`caddy:2-builder-alpine` and `caddy:2-alpine` are build bases. The running proxy is built in this repo with the Cloudflare DNS plugin (`github.com/caddy-dns/cloudflare`) via `xcaddy`. `node:22-alpine` and `python:3.12-slim` are build bases for the dashboard. The dashboard image then installs, during `docker compose build`:

- npm: `react`, `react-dom`, `react-router-dom`, `@fontsource/fraunces`, `@fontsource/outfit`, and the Vite/Tailwind build tools in `dashboard/frontend/package.json`
- pip: `fastapi`, `uvicorn`, `redis` from `dashboard/backend/requirements.txt`

The executor image uses `python:3.12-slim` and the Python standard library only. The DNS updater container uses that same image. It reads `CLOUDFLARE_API_TOKEN` and updates the A records for the hostnames in `.env` when the home address changes. No extra package is installed for it.

Media:

```bash
docker pull jellyfin/jellyfin:10.10.7
```

Git:

```bash
docker pull postgres:16-alpine
docker pull codeberg.org/forgejo/forgejo:11
```

Collaboration:

```bash
docker pull postgres:16-alpine
docker pull nextcloud:31-apache
docker pull collabora/code:latest
```

`collabora/code:latest` is the value of `COLLABORA_IMAGE` in `.env.example`. Pin a version there when you want builds to stop moving.

Games:

```bash
docker pull itzg/minecraft-server:java21
```

The Minecraft image downloads the server jar on first start. That download is inside the container, after `sudo bash scripts/up.sh games`, and only if `MINECRAFT_EULA=TRUE`.

AI:

```bash
docker pull vllm/vllm-openai:latest
docker pull nvidia/dcgm-exporter:latest
docker pull python:3.12-slim
```

`nvidia/dcgm-exporter:latest` is `GPU_EXPORTER_IMAGE`. Building LLMLingua (`sudo bash scripts/up.sh ai`) also runs:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install fastapi uvicorn pydantic llmlingua
```

That PyTorch wheel is large and is CPU-only. vLLM uses the GPU. Model weights are a separate download the first time vLLM starts, using the id in `VLLM_MODEL`. They land in the Docker volume for that container, on the NVMe with the other Docker data.

Discord:

```bash
docker pull ghcr.io/lavalink-devs/lavalink:4
docker pull python:3.12-slim
```

The bot image then pip-installs `discord.py`, `wavelink`, and `PyNaCl`.

`scripts/configure-sso.sh` downloads the Jellyfin SSO plugin the first time the media profile is up:

```bash
curl -fsSL https://api.github.com/repos/9p4/jellyfin-plugin-sso/releases/latest
```

That response names a `.zip` asset. The script downloads and unpacks it. You do not run the curl by hand.

Deploy:

```bash
docker pull postgres:15-alpine
docker pull redis:7-alpine
docker pull coollabsio/coolify:latest
docker pull coollabsio/coolify-realtime:1.0.19
```

`coollabsio/coolify:latest` is `COOLIFY_IMAGE`. `coollabsio/coolify-realtime:1.0.19` is the websocket service Coolify expects. Postgres 15 is only for Coolify. The rest of the stack uses Postgres 16.

Codegraph is optional and is not started by a profile:

```bash
sudo bash scripts/optional/install-codegraph.sh
```

That downloads `codegraph-linux-x64.tar.gz` or `codegraph-linux-arm64.tar.gz`, checks `SHA256SUMS`, and installs the launcher. Index one repository with `sudo bash scripts/optional/index-repo.sh /path/to/repo`. The script refuses if `.env`, a private key, or `credentials.json` is present and not gitignored.

Cache (second address on the server VLAN, never Caddy's port 80):

```bash
docker pull lancachenet/monolithic:latest
```

---

# 3. Name the site before the first start

Open `.env.example` and replace every `example.com` with your real domain. Set a real mailbox for certificates and the first admin.

```text
DOMAIN=example.com
ACME_EMAIL=you@example.com
DASHBOARD_HOST=dashboard.example.com
AUTH_HOST=auth.example.com
MEDIA_HOST=media.example.com
GIT_HOST=git.example.com
FILES_HOST=files.example.com
OFFICE_HOST=office.example.com
APPS_HOST=apps.example.com
NOTIFY_HOST=notify.example.com
GRAFANA_HOST=grafana.example.com
AUTHENTIK_BOOTSTRAP_EMAIL=you@example.com
```

Leave the password lines empty. `scripts/setup.sh` fills those.

If these names are still `example.com` when setup runs, Caddy uses a private certificate and the public internet cannot trust the site. You can fix that later by editing `.env` and running `sudo bash scripts/up.sh core`, but setting the names now avoids a second certificate attempt.

---

# 4. Cloudflare DNS and the API token

Do this in a browser on your PC. The server does not have a desktop.

1. Add the domain to Cloudflare and point the registrar at Cloudflare's nameservers.
2. Create an A record for each hostname you set above. The content is your home's public IPv4 address. Turn the proxy on (orange cloud) for all of them.
3. Create an API token with Zone.Zone read and Zone.DNS edit on this domain only.
4. Put that token in `.env.example` as `CLOUDFLARE_API_TOKEN`. It is a secret. It stays in `.env` on the server and is never committed.

Minecraft is not one of these records. Port `25565` is a direct forward and is not covered by the Cloudflare proxy.

Caddy uses the token for the DNS challenge, so certificates can be issued while the orange cloud is on. The core profile's DNS updater uses the same token to refresh those A records when the home address changes. Create the records first. The updater does not create missing ones.

---

# 5. Forward the public ports

On OPNsense, forward to `192.168.50.10`:

```text
TCP 80    -> 192.168.50.10:80
TCP 443   -> 192.168.50.10:443
TCP 25565 -> 192.168.50.10:25565
```

Skip 25565 until you enable the games profile. Do not forward 22 or any application port.

---

# 6. Format the bay SSD and start the core

The NVMe already holds Ubuntu. This command formats the other empty disk and will refuse to touch the operating-system disk.

```bash
sudo bash scripts/setup.sh --format-bulk
```

If the bay SSD is not installed yet:

```bash
sudo bash scripts/setup.sh --allow-single-disk
```

Add a disk later with:

```bash
sudo bash scripts/storage/add-disk.sh /dev/disk/by-id/ata-...
```

The first run builds Caddy and the dashboard, then downloads Authentik, Postgres, Redis, Prometheus, Grafana, Loki, and ntfy. That can take a long time. Leave it until the shell prints the bootstrap admin username.

What you should see when it finishes:

```text
/                      NVMe, Ubuntu and Docker
/srv/server/data       NVMe, databases and Authentik
/srv/bulk              bay SSD pool: media, models, worlds, Nextcloud files
```

`/srv/server/media`, `/srv/server/models`, `/srv/server/backups`, and `/srv/server/storage` are links into that pool. Another disk later joins the same pool. New files go to whichever disk has the most free space, and each disk keeps 50 GB unused.

Read the generated password:

```bash
grep AUTHENTIK_BOOTSTRAP_PASSWORD .env
```

The username is `akadmin`. This is the first administrator. It was created by setup, without a referral code.

If Authentik was still starting, the script says so. Wait, then:

```bash
sudo bash scripts/configure-authentik.sh
docker logs server-authentik --tail 50
```

---

# 7. Confirm the core from the server

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'
docker logs server-caddy --tail 40
sudo bash scripts/check.sh
```

These containers should be running:

```text
server-caddy
server-authentik
server-authentik-worker
server-authentik-db
server-dashboard
server-executor
server-redis
server-prometheus
server-grafana
server-loki
server-promtail
server-node-exporter
server-cadvisor
server-ntfy
```

`scripts/check.sh` must not print `FAIL`. A warning that the public URL did not answer from inside the house is normal. Many home routers cannot open their own public address. The phone check in the last section is the one that counts.

If Caddy's logs show a certificate error, the token, the DNS record, or the port forward is wrong. Fix that and run:

```bash
sudo bash scripts/up.sh core
```

---

# 8. Prove it from outside the house

Turn off Wi-Fi on a phone so it uses cellular data.

1. Open `https://dashboard.yourdomain/health`. The page is only `{"status":"online"}`.
2. Open `http://dashboard.yourdomain`. It should jump to `https://`.
3. Open `https://dashboard.yourdomain` and sign in as `akadmin`.
4. Open `https://auth.yourdomain`. Authentik's login page should load.
5. From the phone, or any network that is not your house, SSH to the public IP should fail.

When those five are true, the server is reachable from browsers on the internet. The rest of this guide turns on the other parts of the design.

---

# 9. Create the other founding admins

Sign in to the dashboard. Open Admin.

Create each other founding administrator there, with their own username and password. That action is logged with you as the sponsor. These setup accounts are the only ones created without a referral code.

After that, open self-registration stays off. A new person needs a code:

1. On Admin, issue a referral code. The page shows a signup URL and stores your account as the sponsor.
2. Send that URL. Authentik's token is the invitation id in the link, not the short label in the list.
3. The code is single-use. When the person finishes signup, the dashboard reads their username from Authentik and writes it on that row, with the code, the sponsoring admin, and the time.

Regular users do not see the Admin page and cannot make codes.

## Linux accounts for people on other networks

A dashboard account is not an SSH login. Someone who will administer the machine needs three things, and they can do all of it from a network that is not your house:

1. A Tailscale account on this same tailnet. Invite them in the Tailscale admin console. Do not invite people who only use the website. Anyone on the tailnet can attempt SSH.
2. Tailscale installed on their own computer: https://tailscale.com/download
3. Their own Linux user and SSH public key on the server.

On their computer they print a public key:

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

On the server, install that one line:

```bash
sudo bash scripts/admin/add-ssh-key.sh alice "ssh-ed25519 AAAA... alice@laptop"
```

The script creates the user if needed, adds them to `sudo` and `docker`, and writes `~/.ssh/authorized_keys` mode `600`. They then connect with the address from `tailscale ip -4`:

```powershell
ssh alice@100.100.100.20
```

If MagicDNS is on, `tailscale status` shows a name that works the same way. Keep your own Tailscale session open until their session has logged in. Port 22 stays closed on the public internet and on the home LAN. After the VLAN, the home LAN cannot reach the server either. Tailscale is the path that still works.

---

# 10. Turn on the rest, one profile at a time

Run the next command only after the previous service opens in the browser over HTTPS.

```bash
sudo bash scripts/up.sh media
sudo bash scripts/up.sh git
sudo bash scripts/up.sh collab
```

| Profile | Public name | What you should see |
|---|---|---|
| media | `https://media.yourdomain` | Jellyfin setup, libraries under `/srv/bulk/media` |
| git | `https://git.yourdomain` | Forgejo. Registration is already disabled |
| collab | `https://files.yourdomain` | Nextcloud. The local admin user is `ncadmin`. The password is `NEXTCLOUD_ADMIN_PASSWORD` in `.env` |
| collab | `https://office.yourdomain` | Collabora, used from inside Nextcloud |

Grafana is already in the core profile at `https://grafana.yourdomain`. Sign in with Authentik. Only the administrators group gets in. The local Grafana password is `GRAFANA_ADMIN_PASSWORD` in `.env`, for the case where Authentik login is down.

ntfy is already running at `https://notify.yourdomain`. The admin user is `ntfyadmin`. The password is `NTFY_ADMIN_PASSWORD` in `.env`. The `admin` topic is for that user. The `general` topic can be read without a login. Only the admin user can publish.

These three wait on a value in `.env`:

```bash
# After you accept Minecraft's EULA, set MINECRAFT_EULA=TRUE
sudo bash scripts/up.sh games

# After VLLM_MODEL is a real model id and nvidia-smi works.
# Set VLLM_MANAGER_MODEL as well when you want the smaller always-on manager model.
sudo bash scripts/up.sh ai

# After DISCORD_TOKEN is set
sudo bash scripts/up.sh discord
```

`games` publishes `25565/tcp`. Add the OPNsense forward at that point if you skipped it. The Minecraft page can start, stop, restart, and back up the world. The backup file lands in `/srv/bulk/backups`. `scripts/backup/backup.sh` still copies that world to `BACKUP_TARGET` when you run a full backup. `ai` does not publish vLLM to the internet. Chat goes through the dashboard. When `VLLM_MANAGER_MODEL` is set, a second container starts and the chat model is limited to 65% of GPU memory. `discord` stays on the private network. The bot answers `/server`, `/play`, `/skip`, `/stop`, and `/queue`. YouTube is off. `/play` takes a SoundCloud link or a direct audio URL. The bot does not print the token.

`scripts/up.sh` runs `scripts/configure-sso.sh` after the containers start. That connects Forgejo and Nextcloud to Authentik, and installs the Jellyfin SSO plugin. Jellyfin's own first-run wizard still has to be finished once in the browser. After that, the login page has an Authentik button. Forgejo and Nextcloud keep the passwords in `.env` for the case where Authentik is down.

Coolify is the deploy profile:

```bash
sudo bash scripts/up.sh deploy
```

Its site is `https://apps.yourdomain`. The first login is `admin`. The password is `COOLIFY_ROOT_PASSWORD` in `.env`. Coolify's files live under `/data/coolify` on the server, which is the layout its installer uses. After you create an API token in Coolify, put it in `.env` as `COOLIFY_API_TOKEN` and run `sudo bash scripts/up.sh core`. The Websites page then adds those applications next to `config/websites.json`. If `server-coolify` restarts, read `docker logs server-coolify` before deploying other apps through it. The dashboard does not depend on Coolify.

LanCache is separate because it must not take Caddy's port 80. Give the server a second address, such as `192.168.50.11`, set `LANCACHE_BIND_IP` in `.env`, then:

```bash
sudo bash scripts/up.sh cache
```

The cache is capped by `LANCACHE_DISK_SIZE` (200g unless you change it).

To stop one group without stopping the dashboard:

```bash
sudo bash scripts/down.sh media
```

## Dashboard pages

These routes are in the dashboard now. Signed-in users see the status bar on each of them. Logs and Admin stay in the navigation only for administrators. Processes is visible to every signed-in user. Start, stop, and the model kill switch stay administrator actions.

| Page | Route | What it does today | Room to grow |
|---|---|---|---|
| Home | `/` | Front door after sign-in | Shortcuts and announcements |
| Services | `/services` | Tiles for each running service and its public name | Health detail per service |
| LLMs | `/llms` | Chat with the local model. Administrators also get the manager model when `VLLM_MANAGER_MODEL` is set. Neither model can run commands | More tools that call the existing read-only stats API |
| Websites | `/websites` | Links from `config/websites.json`, plus Coolify applications when `COOLIFY_API_TOKEN` is set | Richer deploy metadata |
| Minecraft | `/minecraft` | Online state, player list, and version. Administrators can start, stop, restart, back up, and read the console | A scheduled world backup |
| Media | `/media` | Link to Jellyfin when `MEDIA_HOST` is set and the media profile is on | Library status |
| Files | `/files` | Link to Nextcloud | Storage usage for that library |
| Git | `/git` | Link to Forgejo | Recent repos |
| Collaboration | `/collaboration` | Links to Nextcloud and Collabora | Shared-document list |
| Notifications | `/notifications` | Explains the admin and general ntfy topics, and links to ntfy when the host is set | Embedded topic view |
| Chat | `/chat` | Shared chat, kept for `CHAT_RETENTION_DAYS` (90 unless changed) | Threads |
| Processes | `/processes` | Container CPU and RAM | GPU column and admin controls |
| Logs | `/logs` | Referral and admin audit rows, plus a Grafana link. Administrators only | Live Loki view |
| Admin | `/admin` | Founding accounts, referral codes, revoke, kill switch. Administrators only | More operator actions |

Add a page by adding a route in `dashboard/frontend/src/App.tsx` and, when it needs data, a matching API in `dashboard/backend/app/main.py`. Keep new public hostnames in `.env.example`, `scripts/render_runtime.py`, and this guide's download section if they pull a new image.

---

# 11. GitHub Pages front door

People can already use `https://dashboard.yourdomain`. The Pages site is the public link that shows a maintenance message when `/health` does not answer.

On your PC, edit `github-pages/config.js`:

```javascript
window.THE_SERVER = {
  healthUrl: "https://dashboard.yourdomain/health",
  enterUrl: "https://dashboard.yourdomain",
};
```

Commit and push. In https://github.com/spencerboggs/home-server , enable Pages and choose GitHub Actions as the source. `.github/workflows/pages.yml` publishes the `github-pages` folder. The health response only contains `{"status":"online"}`, which is all that page is allowed to see.

---

# 12. Backups

A copy on `/srv/bulk` is not a backup. Set `BACKUP_TARGET` in `.env` to a disk or machine that is not this server, then:

```bash
sudo bash scripts/backup/backup.sh
```

Restore that copy once onto a spare folder before you trust the job. The script saves Caddy certificates, Authentik, the dashboard database, Forgejo, Minecraft worlds, and Nextcloud files. Model weights are left out on purpose.

---

# 13. Final check

On the server:

```bash
sudo bash scripts/check.sh
```

Then repeat the phone test from section 8, and open each hostname you enabled. Sign in with an account that is not `akadmin` after you have issued that person a code.

Useful commands after this:

```bash
docker ps
docker logs server-caddy --tail 50
sudo bash scripts/up.sh core
sudo bash scripts/emergency/llm-kill.sh
tailscale ip -4
sudo ufw status verbose
```

`scripts/emergency/llm-kill.sh` stops containers labeled `ai-model=true` and leaves the dashboard, files, and proxy running. The same button is on the dashboard Admin page.

---

# What is running, and what is still unfinished

After section 8, a browser on the public internet can reach the dashboard over HTTPS and sign in. Referral signup writes the new username back onto the sponsoring admin's row. SSH for administrators on other networks is Tailscale plus `scripts/admin/add-ssh-key.sh`. The core profile also keeps Cloudflare A records pointed at the current public address when `CLOUDFLARE_API_TOKEN` is set.

These still need a person, a secret, or the running machine. The repository already contains the code for them.

- Finish Jellyfin's first-run wizard once. SSO is installed by `scripts/configure-sso.sh` after that profile starts. Forgejo and Nextcloud get an Authentik button from the same script. Their local admin passwords stay in `.env`.
- Create a Coolify API token in its UI and set `COOLIFY_API_TOKEN` if the Websites page should list deployed apps. The root password is already generated.
- Set `VLLM_MODEL` and, if you want the manager model, `VLLM_MANAGER_MODEL`, to real Hugging Face ids. The containers are defined. The weights download on first start.
- Set `DISCORD_TOKEN` before the discord profile. `/play` uses Lavalink. YouTube stays off.
- Set `BACKUP_TARGET` and run `scripts/backup/backup.sh` once you have a disk that is not this server. The Minecraft backup button writes a tar on `/srv/bulk/backups` before that off-server copy exists.
- Run `scripts/optional/install-codegraph.sh` when you want the index tool. It is not part of a profile.
