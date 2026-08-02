#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: sh scripts/verify_postgres_restore.sh <backup.dump>" >&2
  exit 1
fi

backup_path=$1
if [ ! -f "$backup_path" ]; then
  echo "Backup file not found: $backup_path" >&2
  exit 1
fi

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
container_name="binance-app-restore-$run_id"
volume_name="binance-app-restore-$run_id"
restore_user="restore_user"
restore_database="restore_db"
restore_password="restore-only-local"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  docker volume rm "$volume_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker volume create "$volume_name" >/dev/null
docker run -d --name "$container_name" \
  -e "POSTGRES_USER=$restore_user" \
  -e "POSTGRES_PASSWORD=$restore_password" \
  -e "POSTGRES_DB=$restore_database" \
  -v "$volume_name:/var/lib/postgresql/data" \
  postgres:17-alpine >/dev/null

ready=false
for _ in $(seq 1 30); do
  if docker exec "$container_name" pg_isready -U "$restore_user" -d "$restore_database" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [ "$ready" != true ]; then
  echo "Temporary restore PostgreSQL did not become ready." >&2
  exit 1
fi

docker cp "$backup_path" "$container_name:/tmp/source.dump"
docker exec "$container_name" pg_restore --exit-on-error --no-owner --no-privileges \
  -U "$restore_user" -d "$restore_database" /tmp/source.dump

table_count=$(docker exec "$container_name" psql -U "$restore_user" -d "$restore_database" -Atc \
  "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('market_candles', 'aggregate_trades', 'ingestion_checkpoints', 'ingestion_runs', 'alembic_version');")
duplicate_candles=$(docker exec "$container_name" psql -U "$restore_user" -d "$restore_database" -Atc \
  "SELECT count(*) FROM (SELECT 1 FROM market_candles GROUP BY symbol, interval, open_time HAVING count(*) > 1) duplicates;")
revision=$(docker exec "$container_name" psql -U "$restore_user" -d "$restore_database" -Atc \
  "SELECT version_num FROM alembic_version LIMIT 1;")

if [ "$table_count" -ne 5 ] || [ "$duplicate_candles" -ne 0 ] || [ -z "$revision" ]; then
  echo "Restore verification failed: tables=$table_count duplicate_candles=$duplicate_candles revision=${revision:-missing}" >&2
  exit 1
fi

docker exec "$container_name" psql -U "$restore_user" -d "$restore_database" -c \
  "SELECT 'market_candles' AS table_name, count(*) AS rows FROM market_candles UNION ALL SELECT 'aggregate_trades', count(*) FROM aggregate_trades UNION ALL SELECT 'ingestion_checkpoints', count(*) FROM ingestion_checkpoints UNION ALL SELECT 'ingestion_runs', count(*) FROM ingestion_runs;"
echo "Restore verification passed: revision=$revision, duplicate_candles=0"
