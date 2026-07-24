#!/usr/bin/env bash
# Run as: sudo bash scripts/setup_db.sh
set -euo pipefail

DB=agentic_rag
USER=agentic
PASS=agentic_secret

echo "Creating PostgreSQL user and database..."

sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${USER}') THEN
    CREATE USER ${USER} WITH PASSWORD '${PASS}';
    RAISE NOTICE 'User created';
  ELSE
    ALTER USER ${USER} WITH PASSWORD '${PASS}';
    RAISE NOTICE 'User password updated';
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE ${DB} OWNER ${USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB}') \gexec

GRANT ALL PRIVILEGES ON DATABASE ${DB} TO ${USER};
SQL

echo "✓ Done — database '${DB}' with user '${USER}'"
