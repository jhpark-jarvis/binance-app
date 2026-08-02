param(
    [string]$BackupDirectory = "backups"
)

$ErrorActionPreference = "Stop"
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$backupName = "binance_ops_$timestamp.dump"
$backupPath = Join-Path $BackupDirectory $backupName

New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$containerId = (docker compose ps -q postgres).Trim()
if ([string]::IsNullOrWhiteSpace($containerId)) {
    throw "postgres service is not running. Start it with: docker compose up -d postgres"
}

$dumpCommand = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --file "/tmp/' + $backupName + '"'
docker compose exec -T postgres sh -c $dumpCommand
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }

docker cp "${containerId}:/tmp/$backupName" $backupPath
if ($LASTEXITCODE -ne 0) { throw "Failed to copy backup from postgres container." }

$removeCommand = 'rm -f "/tmp/' + $backupName + '"'
docker compose exec -T postgres sh -c $removeCommand

$hash = Get-FileHash -Path $backupPath -Algorithm SHA256
"$($hash.Hash) *$backupName" | Set-Content -NoNewline -Path "$backupPath.sha256"

Write-Host "Backup created: $backupPath"
Write-Host "Checksum created: $backupPath.sha256"
