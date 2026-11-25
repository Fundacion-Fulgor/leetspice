# LeetSpice — Deployment Guide

## Prerequisites

- A Linux server (Ubuntu 22.04+ recommended) with **Docker** and **Docker Compose** installed.
- A domain name pointing to the server's public IP (e.g., `leetspice.youruniversity.edu`).
- Ports **80** and **443** open in the firewall.

## Quick Start

### 1. Clone and configure

```bash
git clone <your-repo-url> leetspice && cd leetspice
cp .env.prod.example .env
```

Edit `.env` and **replace every `CHANGE-ME` value**:

| Variable | How to generate |
|---|---|
| `DOMAIN` | Your real domain, e.g. `leetspice.uni.edu` |
| `POSTGRES_PASSWORD` | `openssl rand -base64 24` |
| `WORKER_DB_PASSWORD` | `openssl rand -base64 24` |
| `SECRET_KEY` | `openssl rand -hex 32` |

### 2. Build and start

```bash
docker compose -f compose.prod.yaml up -d --build
```

> First build takes ~10 minutes (compiles Magic, Netgen, OpenVAF, IHP PDK).
> Subsequent builds use Docker cache and are much faster.

### 3. Create an admin user (not with single sign-on, see below)

```bash
docker compose -f compose.prod.yaml exec web \
  python scripts/create_admin.py "admin@uni.edu" "YourPassword" "Admin Name"
```

### 4. Verify

Visit `https://your-domain` — Caddy will have already provisioned a Let's Encrypt TLS certificate automatically.

---

## Architecture

```
Internet → Caddy (:80/:443, auto-HTTPS) → web (:8000, FastAPI/Uvicorn)
                                            ↕
                                           db (PostgreSQL 16)
                                            ↕
                                         worker (judge process, isolated network)
```

## Volumes and Persistence

| Volume | Contains | Backup priority |
|---|---|---|
| `postgres_data` | All users, submissions, scores | **Critical** |
| `challenges_data` | Challenge files (judge, specs, assets) | High |
| `worker_data` | Temporary verification scratch files | Low |
| `caddy_data` | TLS certificates | Medium |

### Backing up the database

```bash
docker compose -f compose.prod.yaml exec db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup_$(date +%F).sql
```

## Single sign-on (Authentik forward auth)

LeetSpice can take its accounts and roles from Authentik. Caddy asks Authentik's embedded outpost about every request (`forward_auth`) and, when the user is allowed in, copies the outpost's identity headers onto the request it proxies to the app. `Caddyfile.authentik.example` is a working Caddyfile for this (plain HTTP behind a Cloudflare tunnel; adjust the site address and the outpost address).

1. In Authentik create a **Proxy provider** in *forward auth (single application)* mode for the public URL and an Application for it; bind the policy that decides who may open LeetSpice to the application.
2. Create the Authentik groups `leetspice-admin` and `leetspice-tester`.
3. Generate a secret with `openssl rand -hex 32` and set in `.env`: `SSO_ENABLED=true` and `SSO_PROXY_SECRET=<secret>`. The same value reaches Caddy through the `caddy` service in `compose.prod.yaml`. The app refuses to start with `SSO_ENABLED=true` and no secret.
4. Use `Caddyfile.authentik.example` as the Caddyfile.

How it behaves:

- The LeetSpice account is created on a person's first request and keyed by Authentik's stable user id (`X-authentik-uid`). Email, name and username are refreshed on every request. A pre-existing local account is linked on first sign-in only when its email matches the Authentik email exactly (ignoring case); after that the uid is the key, so an email change in Authentik does not create a second account. If the email already belongs to an account linked to a different Authentik user, the request gets a 409 and an administrator has to resolve it.
- Role: members of `leetspice-admin` are admins and members of `leetspice-tester` are testers, evaluated on every request. Removing someone from a group takes the role away on their next request.
- Trust: the app reads the identity headers only from requests that carry `X-Leetspice-Proxy-Secret` with the right value (Caddy overwrites that header on every request it proxies). Requests without it, or without the identity headers, get a 403. Only the headers named in Caddy's `copy_headers` are read; Caddy removes any client-supplied copy of those before adding the outpost's values. `/health` is exempt so the container health check works.
- Local sign-up, local login, display-name and password changes are switched off. "Log out" ends the Authentik session.
- There is no password break-glass while SSO is on. To recover admin rights, add the person to `leetspice-admin` in Authentik. If Authentik itself is down, stop the stack, set `SSO_ENABLED=false` and start it again: local accounts that were linked keep their old password.

## Security Notes

- **No exposed database port**: PostgreSQL is only reachable by web and worker containers.
- **Worker isolation**: The worker runs on an `internal` Docker network with no internet access, limited to 1.5 CPUs, 1 GB RAM, and 256 PIDs.
- **Secure cookies**: Session cookies are set with `Secure`, `HttpOnly`, and `SameSite=Lax` flags in production.
- **CSRF protection**: All state-changing forms require a signed CSRF token.
- **Security headers**: Caddy adds `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, and more.
- **Rate limiting**: 30 requests/minute per IP (configurable in `main.py`).
- **Upload size limit**: 10 MB maximum request body.

## Updating

```bash
git pull
docker compose -f compose.prod.yaml up -d --build
```

The web container runs `alembic upgrade head` on startup, so database migrations are applied automatically.
