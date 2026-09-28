-- Production database initialization
-- The WORKER_DB_PASSWORD env var is set on the postgres container.
-- We use `\set` + `\getenv` (psql ≥ 14) to parameterize it.

\getenv worker_pw WORKER_DB_PASSWORD

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'leetspice_worker') THEN
    EXECUTE format('CREATE USER leetspice_worker WITH PASSWORD %L', current_setting('app.worker_pw', true));
  END IF;
END
$$;

-- Set the password via a session variable so the DO block can read it
SELECT set_config('app.worker_pw', :'worker_pw', false);

DO $$
BEGIN
  EXECUTE format('ALTER USER leetspice_worker WITH PASSWORD %L', current_setting('app.worker_pw'));
END
$$;

GRANT CONNECT ON DATABASE :"POSTGRES_DB" TO leetspice_worker;

-- Switch to the application database for schema grants
\c :"POSTGRES_DB"
GRANT USAGE ON SCHEMA public TO leetspice_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO leetspice_worker;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO leetspice_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO leetspice_worker;
