#!/bin/sh
set -e
echo "Running migrations..."
python manage.py migrate --no-input
echo "Copying master.yaml to PVC..."
cp /webapp/deploy/bootstrap/master.yaml /webapp/myapp/media/user_osm_files/master.yaml
echo "Starting application..."
exec "$@"