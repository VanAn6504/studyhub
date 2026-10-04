[CmdletBinding()]
param([switch]$EnvironmentOnly)

$ErrorActionPreference = 'Stop'
$taskProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskProjectRoot

function New-LocalSecret {
    $taskRandomBytes = New-Object byte[] 32
    $taskGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $taskGenerator.GetBytes($taskRandomBytes) } finally { $taskGenerator.Dispose() }
    return [BitConverter]::ToString($taskRandomBytes).Replace('-', '').ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath '.env')) {
    $taskEnvironmentText = Get-Content -LiteralPath '.env.example' -Raw -Encoding UTF8
    $taskDatabaseSecret = New-LocalSecret
    $taskEnvironmentText = $taskEnvironmentText.Replace('CHANGE_ME_DATABASE_PASSWORD', $taskDatabaseSecret)
    $taskEnvironmentText = $taskEnvironmentText.Replace('CHANGE_ME_JWT_SECRET', (New-LocalSecret))
    $taskEnvironmentText = $taskEnvironmentText.Replace('CHANGE_ME_TEACHER_PASSWORD', (New-LocalSecret))
    $taskEnvironmentText = $taskEnvironmentText.Replace('CHANGE_ME_STUDENT_PASSWORD', (New-LocalSecret))
    [IO.File]::WriteAllText((Join-Path $taskProjectRoot '.env'), $taskEnvironmentText, [Text.UTF8Encoding]::new($false))
    Write-Host 'Created local .env with random passwords and JWT secret. Existing .env is never overwritten.'
}
if ($EnvironmentOnly) { return }

& docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop, wait until its engine is ready, then run this script again.' }
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose startup failed. Check docker compose logs.' }
& docker compose exec -T backend python -m app.seed
if ($LASTEXITCODE -ne 0) { throw 'Seed failed. Check bootstrap variables in .env and backend logs.' }

Write-Host 'StudyHub: http://localhost:5173'
Write-Host 'API docs: http://localhost:8000/api/docs'
Write-Host 'Teacher: BOOTSTRAP_TEACHER_EMAIL; student: DEMO_STUDENT_EMAIL in .env.'
Write-Host 'Read the generated passwords in .env. Keep this file local.'
