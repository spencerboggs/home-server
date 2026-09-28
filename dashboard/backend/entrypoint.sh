#!/bin/sh
set -eu
mkdir -p /var/lib/dashboard
chown -R app:app /var/lib/dashboard
exec su -s /bin/sh app -c 'exec uvicorn app.main:app --host 0.0.0.0 --port 8000'
