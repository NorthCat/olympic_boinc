#!/bin/sh
# Container start: migrations, import of the CSV file if it is there, then the API.
# The sync with BoincStats does not run in the container (its Cloudflare check does not pass here).
set -e

alembic upgrade head

IMPORT_FILE="${IMPORT_FILE:-dumps/import.csv}"
if [ -f "$IMPORT_FILE" ]; then
    python -m olympic_boinc.csv_transfer import "$IMPORT_FILE"
else
    echo "no import file $IMPORT_FILE, skipping the import"
fi

# exec: uvicorn becomes the main process and gets SIGTERM from `docker stop`.
exec uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000 "$@"
