# Ladder Content OS — Deployment Guide

## Target

Ubuntu 24.04 VPS (tested on DigitalOcean 1GB droplet, 512MB insufficient for the build step).

---

## Prerequisites

- [ ] DigitalOcean droplet (or any Ubuntu 24.04 VPS, ≥1GB RAM)
- [ ] Domain name with DNS access (point A record to your VPS IP)
- [ ] Port 80 and 443 open in the cloud firewall (DO → Networking → Firewalls)
- [ ] Supabase project with Auth enabled and Google OAuth configured
- [ ] GitHub personal access token (or SSH key) for cloning the repo

### DNS Configuration

In your domain registrar's DNS panel, create an **A record** pointing your domain (and `www` subdomain) to your VPS IP:

| Type | Name | Value |
|---|---|---|
| A | `@` | `168.144.91.147` |
| A | `www` | `168.144.91.147` |

Wait 5–30 minutes for DNS propagation before proceeding with HTTPS setup.

### Supabase Auth configuration

In Supabase Dashboard → Authentication → URL Configuration:

| Field | Value |
|---|---|
| Site URL | `https://<your-domain.com>` |
| Redirect URLs | `https://<your-domain.com>/auth/callback` |

> Use `https://` — Certbot will provision a certificate in Step 8.

---

## Step 1: Install system deps

```bash
apt update && apt upgrade -y
apt install -y python3-venv python3-pip nodejs npm nginx git certbot python3-certbot-nginx

# Playwright deps
apt install -y libnss3 libnspr4 libatk-bridge2.0-0t64 libatk1.0-0t64 libcups2t64 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 libasound2t64
```

> **Note:** Ubuntu 24.04 ships Python 3.12. The project works with 3.12 despite `.python-version` saying 3.11.

---

## Step 2: Add swap (critical on ≤1GB droplets)

Without swap, `pip install` for CrewAI (chromadb, pyarrow, tokenizers) will get killed by OOM.

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```

---

## Step 3: Clone the repo

```bash
git clone https://<github-token>@github.com/digitalmasterykit-rgb/ladder-content-os.git /opt/ladder
cd /opt/ladder
```

> Commit the `backend/vendor/` folder before cloning. It was initially a nested git repo — delete `backend/vendor/mcp_excalidraw/.git` on your dev machine, commit as regular files, and push.

---

## Step 4: Backend

```bash
cd /opt/ladder/backend

# Add setuptools config to pyproject.toml (prevents flat-layout error)
cat >> pyproject.toml << 'EOF'

[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]
EOF

python3 -m venv venv
source venv/bin/activate
pip install uv
pip install -e .
```

### Create .env

```bash
cp .env.example .env
nano .env
```

Minimum required:

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
ANTHROPIC_API_KEY=sk-ant-...
CORS_ORIGINS=https://<your-domain.com>
```

For Google OAuth, additional env vars may be needed depending on your Supabase project setup.

### Research agent env

The vendored research MCP agent runs from `/opt/ladder/backend/vendor/mcp_Research_agent`.
Its `.env` is not committed, so create it on the droplet if you keep research-only keys there:

```bash
cd /opt/ladder/backend/vendor/mcp_Research_agent
cp .env.example .env
nano .env
```

Minimum viable research setup:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
```

Optional but useful:

```env
EXA_API_KEY=exa-...
SCRAPE_CREATORS_API_KEY=sc-...
SUPADATA_API_KEY=supa_...
YOUTUBE_API_KEY=AIza...
APIFY_API_KEY=apify-...
```

If you only set `SCRAPECREATORS_API_KEY` in backend `.env`, also set
`SCRAPE_CREATORS_API_KEY` for the research agent. Restart after changes:

```bash
systemctl restart ladder-backend
```

---

## Step 5: Build Excalidraw canvas

```bash
cd /opt/ladder/backend/vendor/mcp_excalidraw
npm install && npm run build

cd /opt/ladder/backend/excalidraw_headless
npm install && npx playwright install chromium
```

---

## Step 6: Frontend (build locally, upload)

The frontend build needs ~2GB RAM and will OOM on droplets under 2GB. Build on your local machine:

```powershell
# Local Windows machine
cd D:\Development\Zero\ladder\ladder\frontend
cat > .env << 'EOF'
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
VITE_API_URL=
EOF
npm run build
scp -r dist root@168.144.91.147:/opt/ladder/frontend/
```

> **Important:** `VITE_API_URL=` must be empty — nginx serves both frontend and backend on the same origin, so API calls go to `/` without a separate host.

---

## Step 7: Systemd service

```bash
cat > /etc/systemd/system/ladder-backend.service << 'EOF'
[Unit]
Description=Ladder Content OS Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ladder/backend
Environment=PATH=/opt/ladder/backend/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/ladder/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ladder-backend
```

Verify:

```bash
curl http://127.0.0.1:8000/health
# → {"status":"ok"}
```

---

## Step 8: Nginx (HTTP first, then HTTPS)

Replace `<your-domain.com>` with your actual domain in the config below:

```bash
cat > /etc/nginx/sites-available/ladder << 'NGINXEOF'
upstream ladder_backend { server 127.0.0.1:8000; }
server {
    listen 80;
    server_name <your-domain.com> www.<your-domain.com>;
    root /opt/ladder/frontend/dist;
    index index.html;

    # WebSocket
    location /ws/ { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_read_timeout 3600s; proxy_send_timeout 3600s; }

    # Auth API routes (NOT pages — /auth/callback, /auth/reset-password are SPA routes)
    location /auth/me      { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; }
    location /auth/profile  { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; }
    location /auth/onboard  { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; }
    location /auth/avatar   { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; }

    # Other API routes
    location /ideas       { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; }
    location /studio-sessions { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; }
    location /health      { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; }
    location /diagram     { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
    location /knowledge   { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
    location /admin       { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
    location /brands      { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
    location /settings    { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }
    location /videos      { proxy_pass http://ladder_backend; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; }

    # SPA fallback — serves /auth/callback, /make, /studio/*, etc.
    location / { try_files $uri $uri/ /index.html; }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/ladder /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

> **Critical:** Do NOT use a blanket `location /auth { }` proxy — it hijacks frontend SPA routes `/auth`, `/auth/callback`, `/auth/reset-password`. Only proxy the specific API endpoints under `/auth/`.

---

## Step 9: HTTPS with Certbot (Let's Encrypt)

```bash
# Obtain and install certificate (auto-configures nginx)
certbot --nginx -d <your-domain.com> -d www.<your-domain.com>

# Test auto-renewal (certificate renews every 90 days)
certbot renew --dry-run
```

Certbot modifies your nginx config to add the `listen 443 ssl` block and HTTP→HTTPS redirect. Verify:

```bash
curl -I https://<your-domain.com>
# → HTTP/2 200
```

> **WebSocket note:** Certbot's nginx plugin preserves your existing `location /ws/` block. If you ever manually edit the nginx config after running Certbot, run `nginx -t` before reloading.

---

## Common issues & fixes

### `pip install -e .` fails with "Multiple top-level packages"
Pyproject.toml is missing setuptools config. Add the `[build-system]` and `[tool.setuptools.packages.find]` blocks from Step 4.

### `pip install -e .` gets Killed
Out of memory. Add swap: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`

### `npm run build` gets Killed / Aborted
Node heap OOM. Build on your local machine and `scp` the `dist` folder.

### `curl http://127.0.0.1:8000/health` returns "Connection refused"
Check logs: `journalctl -u ladder-backend -n 30`. Usually missing env vars in `.env`.

### `/auth/callback` returns `{"detail":"Not Found"}`
Nginx is proxying the page to the backend. Make sure `/auth/callback` isn't matched by a blanket `location /auth` proxy rule. Only proxy specific API routes (`/auth/me`, `/auth/profile`, `/auth/onboard`, `/auth/avatar`).

### Google login redirects to wrong URL
Update Supabase Dashboard → Authentication → URL Configuration → Site URL and Redirect URLs with your actual domain (use `https://`).

### Certbot fails with "Connection refused" or timeout
DNS hasn't propagated yet, or port 80 isn't open. Verify: `dig <your-domain.com>` should return your VPS IP. Also check your cloud firewall allows port 80 and 443.

### WebSocket connection fails after HTTPS
Certbot may have removed the WebSocket upgrade headers from your config. Check `/etc/nginx/sites-available/ladder` to ensure the `/ws/` location block still has `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`.

---

## Redeploy backend

```bash
# On droplet — pull and restart
ssh root@168.144.91.147 "cd /opt/ladder && git pull"
 git checkout -- frontend/tsconfig.tsbuildinfo && git pull
ssh root@168.144.91.147 "cd /opt/ladder/backend && source venv/bin/activate && pip install -e ."

ssh root@168.144.91.147 "systemctl restart ladder-backend"
```

 Replace your-new-key with the actual key.

  If the key isn't already in .env and you need to add it:

  ssh root@168.144.91.147 "echo 'SCRAPECREATORS_API_KEY=nUO5N23HcLPIzF9y2ICATouZZWG2' >> /opt/ladder/backend/.env && systemctl restart ladder-backend"

  Verify it took effect:

  ssh root@168.144.91.147 "curl http://127.0.0.1:8000/health"


Verify:

```bash
ssh root@168.144.91.147 "curl http://127.0.0.1:8000/health"
# → {"status":"ok"}
```

## Redeploy frontend

Build locally (too memory-intensive for the droplet), then upload as a single tarball to avoid connection resets from hundreds of individual SCP transfers.

```powershell
# 0. ⚠️  Set production values in frontend/.env BEFORE building
#    Open D:\Development\Zero\ladder\ladder\frontend\.env and verify:
#
#      VITE_API_URL=                          ← must be EMPTY (nginx proxies on same origin)
#      VITE_EXCALIDRAW_CANVAS_URL=            ← must be EMPTY (port 3000 is internal-only on droplet)
#
#    Your local dev values are:
#      VITE_API_URL=http://127.0.0.1:8000
#      VITE_EXCALIDRAW_CANVAS_URL=http://127.0.0.1:3000
#
#    After deploying, restore them so local dev still works:
#      VITE_API_URL=http://127.0.0.1:8000
#      VITE_EXCALIDRAW_CANVAS_URL=http://127.0.0.1:3000

# 1. Build
cd D:\Development\Zero\ladder\ladder\frontend
npm run build

# 2. Package into a single tarball
tar -czf dist.tar.gz -C dist .

# 3. Upload (limit bandwidth to 250KB/s to stabilize flaky connections)
scp -o ServerAliveInterval=30 -o TCPKeepAlive=yes -l 2000 dist.tar.gz root@168.144.91.147:/root/

# 4. Extract into the nginx-served dist directory and clean up
ssh root@168.144.91.147 "cd /opt/ladder/frontend/dist && rm -rf * && mv /root/dist.tar.gz . && tar -xzf dist.tar.gz && rm dist.tar.gz"

# 5. ✅  Restore your local dev .env values now (see step 0 above)
```

> **Important:** `VITE_API_URL=` must be empty in `.env` — nginx proxies API routes to the backend on the same origin. Also, the tarball must be extracted into the `dist/` subdirectory (`/opt/ladder/frontend/dist/`), NOT the frontend root, since that's what nginx points to.
>
> **`VITE_EXCALIDRAW_CANVAS_URL` must also be empty for production.** Locally it points to `http://127.0.0.1:3000` (the MCP canvas) so you can watch the diagram draw live. On the droplet, port 3000 is internal-only and not reachable by the browser — leaving it set would show a black iframe instead of the completed scene. Empty = the modal gracefully waits and shows the final scene once generation is done.

If SCP fails mid-transfer, just re-run it — the `rm -rf *` only happens in the SSH step after upload succeeds. The `-l 2000` bandwidth cap and keepalive options prevent most connection resets.

---

## Cheatsheet

| What | Command |
|---|---|
| Backend status | `systemctl status ladder-backend` |
| Backend logs (live) | `journalctl -u ladder-backend -f` |
| Backend logs (recent) | `journalctl -u ladder-backend -n 50` |
| Restart backend | `systemctl restart ladder-backend` |
| Nginx access log | `tail -f /var/log/nginx/access.log` |
| Nginx error log | `tail -f /var/log/nginx/error.log` |
| Reload nginx | `systemctl reload nginx` |
| Test health | `curl http://127.0.0.1:8000/health` |
| Certbot renew | `certbot renew` |
| Free memory | `free -h` |
| Swap usage | `swapon --show` |

---

## Architecture

```
Browser
  │
  ▼
┌──────────────────────┐
│ Nginx :443 (HTTPS)   │  ← Certbot auto-managed SSL
│ Nginx :80 → :443     │  ← HTTP→HTTPS redirect (Certbot adds this)
│ /                    │ → /opt/ladder/frontend/dist/index.html (SPA)
│ /auth/me             │ → proxy to backend :8000
│ /auth/callback       │ → SPA fallback (frontend handles)
│ /ws/                 │ → WebSocket proxy to backend :8000 (WSS)
│ /ideas               │ → proxy to backend :8000
│ ...                  │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Uvicorn :8000        │  (127.0.0.1 only)
│ FastAPI + CrewAI     │
│ Auto-starts:         │
│  - Canvas :3000      │
│  - Headless Playwright│
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Supabase (cloud)     │
│ Auth + DB + Storage  │
└──────────────────────┘
```
