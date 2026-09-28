# LeetSpice Deployment Guide

This guide explains how to deploy LeetSpice to a production server using Docker Compose and Caddy for automatic HTTPS.

## 1. Prerequisites

- A Linux server with Docker and Docker Compose (or Podman Compose) installed.
- A registered domain name pointing to your server's IP address (e.g., `leetspice.youruniversity.edu`).

## 2. Setup Configuration

Clone the repository on your server, then copy the environment template:

```bash
cp .env.prod.example .env
```

Edit the `.env` file and set the following critical values:
- `DOMAIN`: Your actual domain name (Caddy will automatically provision Let's Encrypt SSL certificates for this domain).
- `POSTGRES_PASSWORD`: Generate a strong password.
- `SECRET_KEY`: Generate a long, random string (e.g., `openssl rand -hex 32`).

## 3. Build and Start the Application

Start the containers using the production compose file:

```bash
# Using docker
docker compose -f compose.prod.yaml up -d --build

# Using podman
podman compose -f compose.prod.yaml up -d --build
```

Wait a few minutes for the `web` and `worker` containers to build and start. Caddy will automatically request an SSL certificate for your domain.

## 4. Create an Admin User

To access the admin panel, you need an administrator account. You can create one using the provided script inside the web container:

```bash
docker compose -f compose.prod.yaml exec web python scripts/create_admin.py "admin@youruniversity.edu" "SuperSecret123!" "Admin"
```

## 5. Persistence and Backups

The `compose.prod.yaml` uses named Docker volumes to persist data:
- `postgres_data`: Contains all user accounts, submissions, and challenge metadata.
- `challenges_data`: Contains the actual physical files for the challenges (`.gds`, `.sch`, `.cir`, `judge/` directory, etc.).
- `worker_data`: Contains temporary files generated during verification.
- `caddy_data` / `caddy_config`: Contains your SSL certificates.

**Backups**: You should periodically back up the `postgres_data` volume (e.g., using `pg_dump`) and the `challenges_data` volume.

## 6. Worker Resource Limits

By default, the `worker` container is restricted to 1.5 CPUs and 1GB of RAM to prevent student submissions (like infinite loops or huge meshes) from crashing the server. You can adjust these limits in `compose.prod.yaml` under the `deploy.resources.limits` section.
