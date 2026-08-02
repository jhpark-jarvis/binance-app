param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
    throw "Backup file not found: $BackupPath"
}

$runId = "$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))-$PID"
$containerName = "binance-app-restore-$runId"
$volumeName = "binance-app-restore-$runId"
$restoreUser = "restore_user"
$restoreDatabase = "restore_db"
$restorePassword = "restore-only-local"

function Remove-RestoreTarget {
    docker rm -f $containerName 2>$null | Out-Null
    docker volume rm $volumeName 2>$null | Out-Null
}

try {
    docker volume create $volumeName | Out-Null
    docker run -d --name $containerName `
        -e "POSTGRES_USER=$restoreUser" `
        -e "POSTGRES_PASSWORD=$restorePassword" `
        -e "POSTGRES_DB=$restoreDatabase" `
        -v "${volumeName}:/var/lib/postgresql/data" `
        postgres:17-alpine | Out-Null

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        docker exec $containerName pg_isready -U $restoreUser -d $restoreDatabase *> $null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "Temporary restore PostgreSQL did not become ready." }

    docker cp $BackupPath "${containerName}:/tmp/source.dump"
    if ($LASTEXITCODE -ne 0) { throw "Failed to copy backup to restore container." }
    docker exec $containerName pg_restore --exit-on-error --no-owner --no-privileges `
        -U $restoreUser -d $restoreDatabase /tmp/source.dump
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed." }

    $tableCount = (docker exec $containerName psql -U $restoreUser -d $restoreDatabase -Atc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('market_candles', 'aggregate_trades', 'ingestion_checkpoints', 'ingestion_runs', 'alembic_version');").Trim()
    $duplicateCandles = (docker exec $containerName psql -U $restoreUser -d $restoreDatabase -Atc "SELECT count(*) FROM (SELECT 1 FROM market_candles GROUP BY symbol, interval, open_time HAVING count(*) > 1) duplicates;").Trim()
    $revision = (docker exec $containerName psql -U $restoreUser -d $restoreDatabase -Atc "SELECT version_num FROM alembic_version LIMIT 1;").Trim()

    if ($tableCount -ne "5" -or $duplicateCandles -ne "0" -or [string]::IsNullOrWhiteSpace($revision)) {
        throw "Restore verification failed: tables=$tableCount duplicate_candles=$duplicateCandles revision=$revision"
    }

    docker exec $containerName psql -U $restoreUser -d $restoreDatabase -c "SELECT 'market_candles' AS table_name, count(*) AS rows FROM market_candles UNION ALL SELECT 'aggregate_trades', count(*) FROM aggregate_trades UNION ALL SELECT 'ingestion_checkpoints', count(*) FROM ingestion_checkpoints UNION ALL SELECT 'ingestion_runs', count(*) FROM ingestion_runs;"
    Write-Host "Restore verification passed: revision=$revision, duplicate_candles=0"
}
finally {
    Remove-RestoreTarget
}
