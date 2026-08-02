#!/usr/bin/env sh
set -eu

backup_dir=backups
retention_days=0
verify_restore=0

usage() {
  echo "Usage: sh scripts/backup_postgres.sh [backup-directory] [--retention-days DAYS] [--verify-restore]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backup-directory)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      backup_dir=$2
      shift 2
      ;;
    --retention-days)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      retention_days=$2
      shift 2
      ;;
    --verify-restore)
      verify_restore=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      usage
      exit 2
      ;;
    *)
      backup_dir=$1
      shift
      ;;
  esac
done

case "$retention_days" in
  ''|*[!0-9]*) echo "--retention-days must be a non-negative integer" >&2; exit 2 ;;
esac

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_name="binance_ops_${timestamp}.dump"
backup_path="$backup_dir/$backup_name"
partial_path="$backup_path.partial"
lock_dir="$backup_dir/.postgres-backup.lock"

mkdir -p "$backup_dir"
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "Another PostgreSQL backup is already running: $lock_dir" >&2
  exit 1
fi

cleanup() {
  rm -f "$partial_path"
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

container_id=$(docker compose ps -q postgres)
if [ -z "$container_id" ]; then
  echo "postgres service is not running. Start it with: docker compose up -d postgres" >&2
  exit 1
fi
health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")
if [ "$health" != "healthy" ]; then
  echo "postgres service is not healthy (current: $health). Backup was not started." >&2
  exit 1
fi

docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --file "/tmp/$1"' \
  sh "$backup_name"
docker cp "$container_id:/tmp/$backup_name" "$partial_path"
mv "$partial_path" "$backup_path"
docker compose exec -T postgres sh -c 'rm -f "/tmp/$1"' sh "$backup_name"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$backup_path" > "$backup_path.sha256"
  sha256sum -c "$backup_path.sha256"
else
  shasum -a 256 "$backup_path" > "$backup_path.sha256"
  shasum -a 256 -c "$backup_path.sha256"
fi

if [ "$verify_restore" -eq 1 ]; then
  script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
  sh "$script_dir/verify_postgres_restore.sh" "$backup_path"
fi

if [ "$retention_days" -gt 0 ]; then
  find "$backup_dir" -type f -name 'binance_ops_*.dump' -mtime "+$retention_days" -print |
    while IFS= read -r expired_backup; do
      rm -f "$expired_backup" "$expired_backup.sha256"
      echo "Expired backup removed: $expired_backup"
    done
fi

echo "Backup created: $backup_path"
echo "Checksum created: $backup_path.sha256"
if [ "$retention_days" -eq 0 ]; then
  echo "Retention is disabled. No existing backup was deleted."
fi
