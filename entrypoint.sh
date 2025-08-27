#!/bin/sh
set -e

echo "Running migrations..."
python manage.py makemigrations --no-input
python manage.py makemigrations myapp --no-input
python manage.py migrate --no-input

echo "Copying master.yaml to PVC..."
cp /webapp/bootstrap/master.yaml /webapp/media/user_osm_files/master.yaml

echo "Starting application..."
exec "$@"
