# ADR 0001: FastAPI and a persistent PoC worker

- Status: Accepted for proof of concept
- Date: 2026-08-04

## Context

LeetSpice needs a small server-rendered/API-capable web application, PostgreSQL persistence, and asynchronous handling of circuit-design submissions. Local contributors should be able to run it with Python or rootless Podman without operating a message broker or creating a new container for every submission.

Submission processing can become expensive and dangerous when a real simulator consumes user-controlled input. The eventual isolation architecture is not ready, so this decision must not imply a security guarantee.

## Decision

Use FastAPI as the ASGI web framework, served by Uvicorn. Use SQLAlchemy/psycopg with PostgreSQL for persistence. For the PoC, run one prestarted `leetspice-worker` process that obtains work through durable database state. Select execution behavior with `RUNNER_BACKEND`, defaulting to a deterministic mock.

Web, database, and worker run as separate Compose services. Web and worker use the same non-root application image. The worker has a persistent named volume but no Podman socket, and it does not start a container per submission.

## Consequences

FastAPI provides typed request handling, dependency injection, and a direct ASGI test surface while retaining support for Jinja templates. A database-backed queue avoids another service in the PoC and makes job state inspectable. A continuously running worker keeps startup latency low and local operations simple.

The persistent worker does not isolate one job from another. A compromised simulator or malicious input may affect worker state, later jobs, or accessible resources. Therefore the mock backend is the default, and real execution must remain limited to trusted development input. This architecture must not be represented as fully sandboxed.

Database polling also has scaling and contention limits. Job claiming must be transactional, retries idempotent, and abandoned leases recoverable when those behaviors are implemented.

## Follow-up

Replace real submission execution with a bounded pool of prewarmed, single-use sandboxes managed outside the web process. Apply resource limits, no-network policy, minimal privileges, validated I/O, image pinning, and unconditional disposal after each job. Keep the mock backend for tests and development workflows.
