# Arranca el backend con Waitress: conexiones persistentes a la BD y pool precalentado.
# Uso:  .\serve.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$url = "http://127.0.0.1:8000"
$threads = 16

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "manage\.py\s+runserver" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$listener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if ($listener) {
  $listener | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 1
}

# Precalienta los hilos (cada uno abre su conexion a la BD remota).
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command",
  "Start-Sleep -Seconds 4; 1..$threads | ForEach-Object { Start-Process curl.exe -ArgumentList '-s','-o','NUL','$url/api/health/' -WindowStyle Hidden }"

Write-Host "Waitress en $url ($threads hilos). Ctrl+C para detener."
& (Join-Path $root ".venv\Scripts\waitress-serve.exe") --listen=127.0.0.1:8000 --threads=$threads config.wsgi:application
