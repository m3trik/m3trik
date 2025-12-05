$port = 7002
try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect("127.0.0.1", $port)
    $client.Close()
    Write-Host "Port $port is OPEN - Running tests..." -ForegroundColor Green
    python o:\Cloud\Code\_scripts\test_maya_lazy_loading.py
} catch {
    Write-Host "Port $port is CLOSED" -ForegroundColor Red
    Write-Host "Run in Maya: import mayatk; mayatk.openPorts(python=':7002')" -ForegroundColor Yellow
}
