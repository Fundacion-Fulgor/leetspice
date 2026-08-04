# LeetSpice

LeetSpice is a work-in-progress platform for learning analog circuit design through small, testable challenges. The proof of concept uses FastAPI, PostgreSQL, and one persistent submission worker.

The project is developed with support from **Fundación Fulgor**.

## Current status

The current PoC implements local account registration and login, a challenge catalog, constrained SPICE subcircuit submission, asynchronous judging, result pages, and a per-challenge leaderboard. The default deterministic mock judge exercises the complete workflow without claiming to simulate a circuit.

The PoC intentionally does **not** launch a container for each submission. The worker is a prestarted, long-lived process. `RUNNER_BACKEND=mock` is the local default so development does not execute an untrusted simulator workload. See [Security](docs/security.md) before enabling a real runner.

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
| `RUNNER_BACKEND` | Runner selection: `mock` or the experimental `ngspice` backend | `mock` |
| `CHALLENGES_PATH` | Challenge fixture directory | `/app/challenges` in containers |
| `WORKER_DATA_DIR` | Persistent worker scratch/state location | `/var/lib/leetspice` in the worker |
| `POSTGRES_*` | Database name, user, password, and published port | See `.env.example` |
| `WEB_PORT` | Published web port | `8000` |

Generate a development secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Do not commit `.env` or reuse local credentials in a shared deployment.

## Challenges and runner

The demo fixture is at [`challenges/demo-cmos-inverter/challenge.json`](challenges/demo-cmos-inverter/challenge.json), with a public specification and starter SPICE subcircuit beside it. The application currently mirrors this fixture during startup; importing versioned challenge packages is a post-PoC task.

The mock backend provides deterministic development/test outcomes and is not circuit simulation. An experimental ngspice adapter assembles validated submissions into a server-owned testbench and invokes ngspice from the already-running worker. Arbitrary submission execution in that persistent process is not safely isolated, so keep the mock backend enabled outside a controlled local PoC.

## Authentication scope

The intended PoC auth scope is local first-party accounts, password hashing, login/logout, and authorization checks that keep submissions attached to their owner. OAuth, account recovery, email verification, administrator roles, multi-tenancy, and API tokens are out of scope until explicitly designed. Authentication does not make submitted netlists safe to execute.

## Documentation

- [Architecture](docs/architecture.md)
- [Security model and limitations](docs/security.md)
- [ADR 0001: FastAPI and a persistent PoC worker](docs/adr/0001-fastapi-persistent-worker.md)

## License and attribution

License terms have not yet been added to this scaffold. Do not infer a license from repository visibility. LeetSpice acknowledges **Fundación Fulgor** for its support of the project.
