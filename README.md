# LeetSpice

LeetSpice is a Fulgor Foundation project for learning analog circuit design through small, testable challenges. It is a gateway for students to earn Fundación Fulgor scholarships: the highest-ranking students automatically earn scholarships. The proof of concept uses FastAPI, PostgreSQL, and one persistent submission worker.

LeetSpice is a **Fulgor Foundation** project.

## Current status

The current PoC implements local accounts, a 31-challenge catalog, constrained SPICE and bounded GDSII submissions, asynchronous judging, private submission history, per-challenge rankings, and a difficulty-weighted global leaderboard. All 26 electrical challenges run private direct-ngspice testbenches with pinned SG13G2 compact models. The inverter runs nine PVT transient points; several advanced placeholder references currently have narrower real operating-point checks and do not yet claim complete gain, noise, stability, startup, or temperature-coefficient characterization. Five physical challenges run KLayout top-cell inspection, Magic full DRC, Netgen LVS, Magic PEX, and private post-layout ngspice tests.

The PoC intentionally does **not** launch a container for each submission. The worker is a prestarted, long-lived process. The checked-in configuration enables real native EDA verification for controlled first-party use. See [Security](docs/security.md): this worker is not safe for hostile netlists or GDS files.

## Podman quick start

Requirements: Podman, a Compose provider (`podman compose`), and free host ports 8000 and 5432.

```sh
cp .env.example .env
podman compose build
podman compose up -d
podman compose ps
podman compose logs -f web worker
```

Open <http://localhost:8000>. Stop the services without deleting data:

```sh
podman compose down
```

Delete the PostgreSQL and worker volumes as well:

```sh
podman compose down -v
```

Changing `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB` in `.env` does
not update an existing PostgreSQL volume. If the web logs report `password
authentication failed` and the local PoC data can be discarded, recreate the
volumes and start the stack again:

```sh
podman compose down -v
podman compose up -d
```

Do not use `-v` when the database contains data that must be retained. Change
the database role credentials explicitly or restore from a backup instead.

Run only PostgreSQL for host-based Python development:

```sh
podman compose up -d db
```

The stack contains:

- `web`: the non-root FastAPI application container, exposed on `WEB_PORT`.
- `db`: PostgreSQL 16 with a named `postgres_data` volume and readiness check.
- `worker`: one prestarted `leetspice-worker` process with a named `worker_data` volume. It polls work from PostgreSQL and is restarted if its process exits.

`web` and `worker` share an image but run separate commands. Neither receives the Podman socket. Compose waits for PostgreSQL, applies Alembic migrations, checks web health through `/health`, and then starts the worker.

## Local Python development

LeetSpice requires Python 3.12 or newer. With the Compose database running:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
export DATABASE_URL='postgresql+psycopg://leetspice:change-me@localhost:5432/leetspice'
export SECRET_KEY='local-development-only'
export RUNNER_BACKEND='mock'
python -m uvicorn leetspice.main:app --reload
```

Start the persistent worker in another activated shell with the same environment:

```sh
leetspice-worker
```

Run checks:

```sh
python scripts/validate-challenge.py challenges/demo-cmos-inverter/challenge.json
python -m ruff check .
python -m pytest
```

Run a single queued job during development:

```sh
leetspice-worker --once
```

## Configuration

Configuration is environment-driven. `.env.example` documents the Compose inputs and `.env` is ignored by Git.

| Variable | Purpose | Local default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection used by web and worker | Constructed by Compose |
| `SECRET_KEY` | Application signing secret | Insecure development value |
| `RUNNER_BACKEND` | Legacy/fallback netlist runner: `mock` or `ngspice`; manifests select production judges | `ngspice` |
| `CHALLENGES_PATH` | Challenge fixture directory | `/app/challenges` in containers |
| `WORKER_DATA_DIR` | Persistent worker scratch/state location | `/var/lib/leetspice` in the worker |
| `LEETSPICE_JUDGE_TIMEOUT` | ngspice wall-clock timeout | `120` seconds |
| `LEETSPICE_LAYOUT_TIMEOUT` | Per-stage KLayout wall-clock timeout | `300` seconds |
| `POSTGRES_*` | Database name, user, password, and published port | See `.env.example` |
| `WEB_PORT` | Published web port | `8000` |

Generate a development secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Do not commit `.env` or reuse local credentials in a shared deployment.

## Challenges and runner

Every directory below `challenges/` is a strict manifest package. Startup validates its interface, submission kind, backend, specification, starter, public assets, and private references before seeding PostgreSQL. The catalog covers MOS foundations, gain stages, biasing, differential circuits, op amps, dynamic circuits, references, physical design, and capstones. Only manifest-listed assets are downloadable; the application does not expose whole challenge directories.

Netlists are validated before inclusion in private server-owned ngspice decks. Definitions declare test conditions, expected finite measurements, limits, timeouts, and allowlisted score strategies. GDSII uploads are limited to 8 MiB and stored as immutable binary payloads with SHA-256 metadata. The layout judge requires exactly one configured top cell, runs Magic full DRC and Netgen LVS, generates coupled-C or full-RC PEX, then runs a private ngspice deck. Layout score combines electrical merit and compactness. These controls constrain inputs but do not sandbox native EDA tools.

## Authentication scope

The intended PoC auth scope is local first-party accounts, password hashing, login/logout, and authorization checks that keep submissions attached to their owner. OAuth, account recovery, email verification, administrator roles, multi-tenancy, and API tokens are out of scope until explicitly designed. Authentication does not make submitted netlists safe to execute.

## Documentation

- [Architecture](docs/architecture.md)
- [Security model and limitations](docs/security.md)
- [ADR 0001: FastAPI and a persistent PoC worker](docs/adr/0001-fastapi-persistent-worker.md)

## License and attribution

License terms have not yet been added to this scaffold. Do not infer a license from repository visibility. LeetSpice is a **Fundación Fulgor** project.
