$env:UVICORN_PORT = 8000
Write-Host "Open: http://localhost:$env:UVICORN_PORT"
uvicorn app.main:app --reload --host 0.0.0.0 --port $env:UVICORN_PORT
