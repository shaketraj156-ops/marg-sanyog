# One command: start a throwaway backend (own database, fresh seed) and the dev server, run the
# browser smoke test, then stop everything. Your real database is never touched.
#
#   cd frontend
#   powershell -ExecutionPolicy Bypass -File scripts\run-smoke.ps1
$ErrorActionPreference = "Continue"
$frontend = Split-Path -Parent $PSScriptRoot
$backend = Join-Path (Split-Path -Parent $frontend) "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
$tmp = Join-Path $env:TEMP "bp-smoke"
New-Item -ItemType Directory -Force $tmp | Out-Null
Remove-Item "$tmp\smoke.db" -Force -ErrorAction SilentlyContinue

$env:DATABASE_URL = "sqlite:///" + $tmp.Replace('\', '/') + "/smoke.db"
$env:JWT_SECRET = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
$env:CORS_ORIGINS = '["http://localhost:5174"]'   # its own port, so it never clashes with a dev server on 5173
$env:LOGIN_RATE_LIMIT_PER_MINUTE = "1000"   # the walk-through logs in many times from one address
$env:SEED_PASSWORD = "smoke-" + [guid]::NewGuid().ToString("N").Substring(0, 10)

Push-Location $backend
& $py -m alembic upgrade head | Out-Null
& $py -m scripts.seed_synthetic
$api = Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8001" `
    -PassThru -WindowStyle Hidden -RedirectStandardError "$tmp\api.err" -RedirectStandardOutput "$tmp\api.out"
Pop-Location

$env:VITE_API_URL = "http://127.0.0.1:8001"
Push-Location $frontend
$web = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev -- --port 5174 --strictPort" `
    -PassThru -WindowStyle Hidden -RedirectStandardError "$tmp\web.err" -RedirectStandardOutput "$tmp\web.out"

$ready = $false
for ($i = 0; $i -lt 40 -and -not $ready; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        Invoke-RestMethod http://127.0.0.1:8001/health | Out-Null
        Invoke-WebRequest http://localhost:5174 -UseBasicParsing | Out-Null
        $ready = $true
    } catch { }
}
if (-not $ready) { Write-Host "The servers did not start. See $tmp\api.err and $tmp\web.err" }

$code = 1
if ($ready) {
    $env:API_URL = "http://127.0.0.1:8001"
    $env:APP_URL = "http://localhost:5174"
    node scripts/smoke.mjs
    $code = $LASTEXITCODE
}
Pop-Location

# stop the backend and the dev server (including the node process cmd started)
foreach ($p in @($api, $web)) {
    if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F | Out-Null }
}
Remove-Item "$tmp\smoke.db" -Force -ErrorAction SilentlyContinue
exit $code
