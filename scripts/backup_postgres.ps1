param(
    [string]$BackupDirectory = "backups",
    [ValidateRange(0, 3650)]
    [int]$RetentionDays = 0,
    [switch]$VerifyRestore
)

$ErrorActionPreference = "Stop"
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$backupName = "binance_ops_$timestamp.dump"
$backupPath = Join-Path $BackupDirectory $backupName
$partialPath = "$backupPath.partial"
$lockPath = Join-Path $BackupDirectory ".postgres-backup.lock"
$lockCreated = $false

try {
    New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
    try {
        New-Item -ItemType Directory -Path $lockPath -ErrorAction Stop | Out-Null
        $lockCreated = $true
    } catch [System.IO.IOException] {
        throw "Another PostgreSQL backup is already running: $lockPath"
    }

    $containerId = (docker compose ps -q postgres).Trim()
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw "postgres service is not running. Start it with: docker compose up -d postgres"
    }
    $health = (docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $containerId).Trim()
    if ($health -ne "healthy") {
        throw "postgres service is not healthy (current: $health). Backup was not started."
    }

    $dumpCommand = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6 --file "/tmp/' + $backupName + '"'
    docker compose exec -T postgres sh -c $dumpCommand
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }

    docker cp "${containerId}:/tmp/$backupName" $partialPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to copy backup from postgres container." }
    Move-Item -LiteralPath $partialPath -Destination $backupPath -Force

    $removeCommand = 'rm -f "/tmp/' + $backupName + '"'
    docker compose exec -T postgres sh -c $removeCommand

    $hash = Get-FileHash -LiteralPath $backupPath -Algorithm SHA256
   $checksumPath = "$backupPath.sha256"
   "$($hash.Hash) *$backupName" | Set-Content -NoNewline -Encoding ascii -Path $checksumPath
   $expectedHash = ((Get-Content -LiteralPath $checksumPath -Raw -Encoding ascii).Trim() -split '\s+')[0]
   $verifiedHash = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash
   if ($expectedHash -ne $verifiedHash) {
        throw "Checksum content verification failed for $backupPath"
    }

    if ($VerifyRestore) {
       & (Join-Path $PSScriptRoot "verify_postgres_restore.ps1") -BackupPath $backupPath
   }

    if ($RetentionDays -gt 0) {
        $cutoff = (Get-Date).ToUniversalTime().AddDays(-$RetentionDays)
        $expiredBackups = Get-ChildItem -LiteralPath $BackupDirectory -Filter "binance_ops_*.dump" -File |
            Where-Object { $_.LastWriteTimeUtc -lt $cutoff }
        foreach ($expiredBackup in $expiredBackups) {
            Remove-Item -LiteralPath $expiredBackup.FullName -Force
            Remove-Item -LiteralPath "$($expiredBackup.FullName).sha256" -Force -ErrorAction SilentlyContinue
            Write-Host "Expired backup removed: $($expiredBackup.FullName)"
        }
    }

    Write-Host "Backup created: $backupPath"
    Write-Host "Checksum created: $backupPath.sha256"
    if ($RetentionDays -eq 0) {
        Write-Host "Retention is disabled. No existing backup was deleted."
    }
} finally {
    Remove-Item -LiteralPath $partialPath -Force -ErrorAction SilentlyContinue
    if ($lockCreated) {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
}
