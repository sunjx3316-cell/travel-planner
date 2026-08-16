# 启动脚本:读取 .env(若存在)并启动后端服务
$root = Split-Path -Parent $PSScriptRoot

if (Test-Path "$root\.env") {
    Get-Content "$root\.env" | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

Push-Location $root
Write-Host "启动 旅行智规 -> http://127.0.0.1:8000"
$lanIp = & "$root\.venv\Scripts\python.exe" "$root\scripts\get_lan_ip.py" 2>$null
if ($lanIp -and $lanIp -ne "127.0.0.1") {
    Write-Host "手机同 Wi-Fi 访问: http://$lanIp`:8000 (首次需在防火墙放行 Python)"
}
& "$root\.venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
Pop-Location
