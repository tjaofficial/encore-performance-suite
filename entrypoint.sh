#!/bin/sh
set -e

if [ -n "$DB_HOST" ]; then
    echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT:-5432}..."

    python - <<'PY'
import os
import time
import psycopg

host = os.environ["DB_HOST"]
port = int(os.getenv("DB_PORT", "5432"))
dbname = os.getenv("DB_NAME", "encore")
user = os.getenv("DB_USER", "encore")
password = os.getenv("DB_PASSWORD", "")

for attempt in range(60):
    try:
        connection = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=3,
        )
        connection.close()
        print("PostgreSQL is ready.")
        break
    except Exception as exc:
        if attempt == 59:
            raise
        print(f"Database not ready yet: {exc}")
        time.sleep(2)
PY
fi

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

exec "$@"
