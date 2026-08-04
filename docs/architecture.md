# Architecture

## PoC topology

```text
browser/client
      |
      v
FastAPI web  <---->  PostgreSQL  <---->  persistent worker
                                           |
                                           v
                                  mock runner (default)
                                  or configured simulator
```

`compose.yaml` runs three services. The web process handles HTTP and records work in PostgreSQL. PostgreSQL is the durable coordination boundary; no separate broker is required for the PoC. A single worker starts with the stack, claims queued work, invokes the selected backend, and records results. The `worker_data` volume is for worker state and generated artifacts that must survive container restarts; PostgreSQL remains the source of truth for job state.

This design has no per-submission `podman run`, Docker API call, or nested container launch. The worker is not given a container-engine socket. That keeps local setup small but means process lifetime is not an isolation boundary between submissions.

## Runtime contract

- Web entry point: `python -m uvicorn leetspice.main:app --host 0.0.0.0 --port 8000`.
- Liveness/readiness endpoint: unauthenticated `GET /health`, returning a successful HTTP status when the web process can serve requests.
- Worker entry point: the `leetspice-worker` console script.
- Database: PostgreSQL through `DATABASE_URL` using the `postgresql+psycopg` SQLAlchemy dialect.
- Challenge source: versioned fixtures below `CHALLENGES_PATH`.
- Runner selection: `RUNNER_BACKEND`; `mock` is the safe local default.

The image includes ngspice so a deliberately configured simulator backend need not modify the image. Its presence does not mean the application should execute submissions automatically, and it provides no sandboxing.

## Challenge fixtures

Each challenge directory keeps public, seedable assets together:

```text
challenges/<slug>/
  challenge.json
  specification.md
  starter.cir
```

`challenge.json` is UTF-8 JSON with a `schema_version`, stable `slug`, public metadata, starter-file reference, electrical constraints, and public checks. Seeding code may ingest it directly or map those fields into normalized tables. Paths are relative to the fixture directory and must not escape it. `scripts/validate-challenge.py` performs basic structural and path validation; it is not a full JSON Schema validator.

## Deployment boundaries

The supplied stack is for rootless local Podman development, not production. The app image runs as the unprivileged `leetspice` user. Database and worker state use named volumes. Secrets and backend selection enter through environment variables. The host PostgreSQL port is published for development convenience and should not be exposed in a shared environment.

See [Security](security.md) for threat boundaries and the migration path away from the persistent runner.
