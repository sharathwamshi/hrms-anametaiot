param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("dispatch", "clock_in_reminder", "manager_missing_alert", "clock_out_reminder")]
    [string]$Kind
)

$ErrorActionPreference = "Stop"
$secret = [Environment]::GetEnvironmentVariable("INTERNAL_TASK_SECRET")
$envFile = Join-Path $PSScriptRoot ".env"

if (-not $secret -and (Test-Path $envFile)) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*INTERNAL_TASK_SECRET\s*=\s*(.*?)\s*$') {
            $secret = $Matches[1]
            break
        }
    }
}

if (-not $secret) {
    $secret = "dev-internal-secret"
}

$body = @{ kind = $Kind } | ConvertTo-Json
$response = Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:5174/api/attendance/internal/attendance-reminders" `
    -Headers @{ "X-Internal-Secret" = $secret } `
    -ContentType "application/json" -Body $body -TimeoutSec 20

Write-Output ("{0} {1}: {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"), $Kind, ($response | ConvertTo-Json -Compress))
