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

### 3. Create an admin user

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

## Single sign-on (Authentik OIDC)

LeetSpice can offer "Sign in with Fundación Fulgor" through Authentik. Local email/password accounts keep working.

1. In Authentik create an **OAuth2/OpenID Provider** (confidential client) and an Application for it.
2. Set the redirect URI (strict) to `https://<domain>/auth/oidc/callback`.
3. Select the scopes `openid`, `email` and `profile`. The `groups` claim is included by Authentik's default profile scope.
4. Set in `.env`: `OIDC_ISSUER` (e.g. `https://auth.example.org/application/o/<slug>/`), `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`.
5. Optionally set `OIDC_ADMIN_GROUP` to an Authentik group name. Admin rights are synced from the `groups` claim on every OIDC login: members are granted admin and non-members lose it. If empty, OIDC never changes admin rights.

Users are matched by the OIDC subject; the first login of an existing local account with the same email links it. New users are created automatically and cannot use a local password.

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
