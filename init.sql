CREATE USER leetspice_worker WITH PASSWORD 'worker_password';
GRANT CONNECT ON DATABASE leetspice TO leetspice_worker;
\c leetspice
GRANT USAGE ON SCHEMA public TO leetspice_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO leetspice_worker;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO leetspice_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO leetspice_worker;
-- We give the worker basic CRUD on all tables for now, but restrict structural changes.
-- A stricter setup would GRANT only on submission, judge_run, measurement tables.
