# Security model and limitations

## What the PoC does

- Runs the application image as a non-root user.
- Keeps database data and worker state in named volumes.
- Selects database credentials, signing secret, and runner backend through environment variables.
- Defaults to a mock runner, avoiding simulator execution during ordinary UI and workflow development.
- Keeps the Podman socket out of web and worker containers.
- Separates the HTTP and worker processes and uses PostgreSQL as their coordination boundary.

These are useful operational controls. They are **not a sandbox**.

## Persistent-worker risk

The PoC worker is reused across submissions. If a real backend processes user-controlled netlists or GDS files, submissions share a user, process environment, filesystem view, installed tools, network namespace, and persistent volume. Simulator vulnerabilities, malformed native-parser input, pathological geometry, resource exhaustion, stale processes, and cross-job data leakage can affect later jobs or the host-visible service state. Restarting the worker after a failure does not establish a trustworthy security boundary.

Do not expose real-runner submission to untrusted users. This includes the KLayout GDS path even though uploads are size-limited and deck paths are server-owned. Do not mount the container-engine socket, host directories, credentials, or unrelated data into the worker. Do not claim that the non-root UID or container alone provides full sandboxing.

`RUNNER_BACKEND=mock` is the expected mode for public demos until isolation work is complete. Mock results validate product flows, not circuit correctness.

## Authentication boundary

PoC authentication is intended to identify local first-party users and enforce ownership of submissions. Passwords should be stored only as modern password hashes, sessions should use a strong `SECRET_KEY`, and state-changing browser requests require CSRF consideration. Authentication and authorization reduce account-level abuse but do not make a malicious netlist trustworthy.

OAuth, password reset, email verification, administrator workflows, API tokens, organization accounts, and multi-tenant isolation are outside the current scope. Any internet deployment needs those decisions plus TLS, secure cookie settings, rate limits, audit logging, secret management, backups, and database network restrictions.

## Roadmap: prewarmed disposable pool

The target runner architecture is a bounded pool of precreated, disposable sandboxes:

1. A privileged, narrowly scoped pool manager prepares workers from a pinned image; the web application never receives the engine socket.
2. Each job leases one clean sandbox with a unique writable directory and strict CPU, memory, process, wall-clock, output, and disk limits.
3. The sandbox starts with no host mounts, no secrets, a read-only root filesystem where practical, dropped Linux capabilities, `no-new-privileges`, and no network unless a documented need exists.
4. Inputs cross a validated, size-limited interface. Results cross a similarly bounded output interface.
5. The sandbox is destroyed after exactly one job, regardless of success, and replenished asynchronously so latency stays low.
6. Images, simulator versions, policies, and result provenance are pinned and auditable. Failure to apply an isolation control fails the job closed.

Before treating that pool as safe for hostile input, perform threat modeling and adversarial testing appropriate to the chosen runtime. Disposable containers reduce persistence and cross-job leakage; they still should not be marketed as perfect isolation.
