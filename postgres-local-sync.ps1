param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('dump', 'restore')]
    [string]$Mode,

    [string]$BackupFile = (Join-Path (Get-Location) 'supabase-backup.dump'),

    [string]$LocalDatabaseUrl = 'postgresql://postgres:postgres@localhost:5432/iys_sgd_local'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Get-SourceDatabaseUrl {
    if ($env:DATABASE_URL) {
        return $env:DATABASE_URL.Trim()
    }

    $line = Get-Content -LiteralPath '.env' | Where-Object {
        $_ -match '^\s*DATABASE_URL\s*='
    } | Select-Object -Last 1

    if (-not $line) {
        throw 'DATABASE_URL was not found in the environment or .env.'
    }

    return (($line -replace '^\s*DATABASE_URL\s*=\s*', '') -split '#', 2)[0].Trim().Trim('"', "'")
}

function Get-SafeDatabaseDescription([string]$Url) {
    $uri = [Uri]$Url
    return "scheme=$($uri.Scheme) host=$($uri.Host) port=$($uri.Port) database=$($uri.AbsolutePath.TrimStart('/'))"
}

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
    throw 'pg_dump was not found on PATH.'
}

$PgDumpExe = 'pg_dump'
$PgRestoreExe = 'pg_restore'
$Postgres17Bin = 'C:\Program Files\PostgreSQL\17\bin'
if (Test-Path -LiteralPath (Join-Path $Postgres17Bin 'pg_dump.exe')) {
    $PgDumpExe = Join-Path $Postgres17Bin 'pg_dump.exe'
    $PgRestoreExe = Join-Path $Postgres17Bin 'pg_restore.exe'
}
Write-Host "Using backup tool: $(& $PgDumpExe --version)"

if ($Mode -eq 'dump') {
    $sourceUrl = Get-SourceDatabaseUrl
    $BackupFile = [System.IO.Path]::GetFullPath($BackupFile)

    Write-Host "Source database: $(Get-SafeDatabaseDescription $sourceUrl)"
    Write-Host "Writing PostgreSQL-native backup to: $BackupFile"

    & $PgDumpExe --dbname=$sourceUrl --format=custom --no-owner --no-privileges `
        --exclude-schema=graphql --exclude-schema=vault --file=$BackupFile
    if ($LASTEXITCODE -ne 0) {
        throw 'pg_dump failed.'
    }

    Write-Host 'PostgreSQL backup complete.'
    exit 0
}

$BackupFile = [System.IO.Path]::GetFullPath($BackupFile)
if (-not (Test-Path -LiteralPath $BackupFile)) {
    throw "Backup file was not found: $BackupFile"
}

Write-Host "Local database: $(Get-SafeDatabaseDescription $LocalDatabaseUrl)"
Write-Host 'Restoring PostgreSQL-native backup ...'
Write-Host 'The target database must already exist and be empty or disposable.'

$RestoreList = "$BackupFile.restore.list"
& $PgRestoreExe --list $BackupFile |
    Where-Object {
        $_ -notmatch 'pg_graphql|supabase_vault|SCHEMA graphql|SCHEMA vault|TABLE vault\.|TABLE DATA vault\.'
    } |
    Set-Content -LiteralPath $RestoreList -Encoding ascii

& $PgRestoreExe --dbname=$LocalDatabaseUrl --clean --if-exists --no-owner --no-privileges `
    --use-list=$RestoreList $BackupFile
$restoreExitCode = $LASTEXITCODE
Remove-Item -LiteralPath $RestoreList -Force -ErrorAction SilentlyContinue
if ($restoreExitCode -ne 0) {
    throw 'pg_restore failed. Check that the local database exists and credentials are correct.'
}

Write-Host 'Local PostgreSQL restore complete.'
