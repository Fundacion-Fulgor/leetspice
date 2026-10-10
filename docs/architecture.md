# Architecture

## PoC topology

```text
browser/client
      |
      v
FastAPI web  <---->  PostgreSQL  <---->  persistent worker
                                           |
                                           v
                                  direct ngspice characterization
                                  or Magic/Netgen/PEX/ngspice
```

`compose.yaml` runs three services. The web process handles HTTP and records work in PostgreSQL. PostgreSQL is the durable coordination boundary; no separate broker is required for the PoC. A single worker starts with the stack, claims queued work, invokes the selected backend, and records results. The `worker_data` volume is for worker state and generated artifacts that must survive container restarts; PostgreSQL remains the source of truth for job state.

This design has no per-submission `podman run`, Docker API call, or nested container launch. The worker is not given a container-engine socket. That keeps local setup small but means process lifetime is not an isolation boundary between submissions.

## Runtime contract

- Web entry point: `python -m uvicorn leetspice.main:app --host 0.0.0.0 --port 8000`.
- Liveness/readiness endpoint: unauthenticated `GET /health`, returning a successful HTTP status when the web process can serve requests.
- Worker entry point: the `leetspice-worker` console script.
- Database: PostgreSQL through `DATABASE_URL` using the `postgresql+psycopg` SQLAlchemy dialect.
- Challenge source: versioned fixtures below `CHALLENGES_PATH`.
- Challenge manifests select direct ngspice or physical verification; `RUNNER_BACKEND` is a legacy fallback.

The image includes ngspice, KLayout 0.30.3, pinned Magic and Netgen source revisions, and the pinned IHP SG13G2 PDK. Their presence provides verification capability, not a security boundary.

## Challenge fixtures

Each challenge directory is a strict manifest package. Application startup validates every package and aborts rather than silently skipping malformed entries:

```text
challenges/<slug>/
  challenge.json
  specification.md
  starter.cir
  inverter.sch
  inverter.sym
  reference/
```

Netlist submissions remain UTF-8 text. Layout submissions are bounded raw GDSII stored in PostgreSQL as binary data so web and worker need no shared upload filesystem. Challenges declare track, difficulty, interface, submission kind, judge backend/configuration, and public assets. Asset downloads resolve manifest IDs beneath the configured fixture root and never accept arbitrary paths.

Every electrical package has a private direct-ngspice definition and qualified private reference. The inverter uses pinned SG13G2 compact models across nine PVT points. Other packages currently range from functional operating-point tests to family-specific branch/current checks; a real simulation does not imply comprehensive analog signoff, and package specifications state the measured scope.

The layout judge writes each GDS to a temporary workspace, requires exactly one configured top cell, runs Magic full DRC, extracts a capacitance-free LVS netlist, and requires Netgen's unique-match marker against a private reference. Magic then produces a bounded PEX netlist for private ngspice characterization. Temporary workspaces are removed after each run.

## Deployment boundaries

The supplied stack is for rootless local Podman development, not production. The app image runs as the unprivileged `leetspice` user. Database and worker state use named volumes. Secrets and backend selection enter through environment variables. The host PostgreSQL port is published for development convenience and should not be exposed in a shared environment.

See [Security](security.md) for threat boundaries and the migration path away from the persistent runner.
