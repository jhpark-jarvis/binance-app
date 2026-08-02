#!/usr/bin/env sh
set -eu

backup_dir=${1:-backups}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_name="binance_ops_${timestamp}.dump"
backup_path="$backup_dir/$backup_name"

mkdir -p "$backup_dir"
container_id=$(docker compose ps -q postgres)
if [ -z "$container_id" ]; then
  echo "postgres service is not running. Start it with: docker compose up -d postgres" >&2
  exit 1
fi

docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --file "/tmp/$1"' \
  sh "$backup_name"
docker cp "$container_id:/tmp/$backup_name" "$backup_path"
docker compose exec -T postgres sh -c 'rm -f "/tmp/$1"' sh "$backup_name"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$backup_path" > "$backup_path.sha256"
else
  shasum -a 256 "$backup_path" > "$backup_path.sha256"
fi

echo "Backup created: $backup_path"
echo "Checksum created: $backup_path.sha256"
