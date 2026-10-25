param([string]$Email = 'teste@example.invalid')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.env')) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*\WindowsApps\*') {
        & python scripts/configure.py --email $Email
    } else {
        $projectPath = (Get-Location).Path
        docker run --rm --mount "type=bind,source=$projectPath,target=/setup" -w /setup python:3.12.14-slim-bookworm python scripts/configure.py --email $Email
    }
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar configuração; execute scripts/configure.py com um Python funcional.' }
}
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Configuração Docker Compose inválida.' }
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Falha ao iniciar o ambiente; consulte docker compose logs.' }
Write-Host 'n8n: http://localhost:5679 | Painel: http://localhost:8501'
Write-Host 'Painel em modo local de testes. Configure OAuth Gmail antes de ativar fluxos.'
