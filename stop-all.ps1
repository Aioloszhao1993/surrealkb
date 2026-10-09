# SurrealVideo 一键全部关闭（后端 + 前端 + MySQL）
# 用法：在 PowerShell 中执行  cd D:\video_fastqpi ; .\stop-all.ps1
#      或直接双击同目录的 stop-all.bat

Write-Host "=======================================" -ForegroundColor Magenta
Write-Host "  Closing SurrealVideo services" -ForegroundColor Magenta
Write-Host "=======================================" -ForegroundColor Magenta

function Stop-ByPort {
    param([int]$Port, [string]$Label)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "  $Label (port $Port): not running" -ForegroundColor DarkGray
        return
    }
    foreach ($c in $conns) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) {
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proc.Id)" -ErrorAction SilentlyContinue |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  $Label (port $Port): stopped PID $($proc.Id)" -ForegroundColor Green
        }
    }
}

# 1) 前端 Vite
Stop-ByPort -Port 5173 -Label "Frontend(Vite)"

# 2) 后端 FastAPI
Stop-ByPort -Port 8000 -Label "Backend(FastAPI)"

# 3) MySQL（优先优雅关闭）
Write-Host "  MySQL: stopping ..." -ForegroundColor Cyan
$mysqladmin = "D:\video_fastqpi\mysql\mysql-8.0.28-winx64\bin\mysqladmin.exe"
if (Get-Process mysqld -ErrorAction SilentlyContinue) {
    if (Test-Path $mysqladmin) {
        & $mysqladmin -u root shutdown 2>$null
        Start-Sleep -Seconds 3
    }
    $left = Get-Process mysqld -ErrorAction SilentlyContinue
    if ($left) {
        $left | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  MySQL: stopped" -ForegroundColor Green
} else {
    Write-Host "  MySQL: not running" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Done. All services are down." -ForegroundColor Green
