# Start the whole app for the demo: backend (FastAPI) and frontend (Vite) in two windows.
#
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
#
# First time only (see README.md): create backend\.venv, copy backend\.env.example to backend\.env,
# and run the seed script once so the demo users exist.
#
# Then open http://localhost:5173 and log in as planner@blockplanner.test.
param(
    [int]$ApiPort = 8000,
    [switch]$Hidden   # no visible windows (used by automated checks)
)

$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$py = Join-Path $backend ".venv\Scripts\python.exe"

function Test-PortInUse([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Path $py)) {
    Write-Host "Missing backend\.venv. Run the setup steps in README.md first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $backend ".env")) -and -not $env:JWT_SECRET) {
    Write-Host "Missing backend\.env. Copy backend\.env.example to backend\.env first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend packages (first run only) ..."
    Push-Location $frontend
    npm install
    Pop-Location
}

# Bring the database up to date (safe to repeat; only adds missing tables).
Push-Location $backend
& $py -m alembic upgrade head
Pop-Location

$style = if ($Hidden) { "Hidden" } else { "Normal" }
$keep = if ($Hidden) { @() } else { @("-NoExit") }

if (Test-PortInUse $ApiPort) {
    Write-Host "Something already listens on port $ApiPort, so the backend is not started again."
} else {
    $apiCommand = "Set-Location '$backend'; & '$py' -m uvicorn app.main:app --reload --port $ApiPort"
    Start-Process powershell -WindowStyle $style -ArgumentList ($keep + @("-Command", $apiCommand)) | Out-Null
}

if (Test-PortInUse 5173) {
    Write-Host "Something already listens on port 5173, so the frontend is not started again."
} else {
    $webCommand = "Set-Location '$frontend'; `$env:VITE_API_URL = 'http://127.0.0.1:$ApiPort'; npm run dev"
    Start-Process powershell -WindowStyle $style -ArgumentList ($keep + @("-Command", $webCommand)) | Out-Null
}

Write-Host ""
Write-Host "Backend:  http://127.0.0.1:$ApiPort/docs"
Write-Host "Frontend: http://localhost:5173   (log in as planner@blockplanner.test)"
Write-Host "To stop, close the two windows (or press Ctrl+C in each)."
