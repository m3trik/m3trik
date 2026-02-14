# Check if Maya command port is open
$port = 7002
try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect("127.0.0.1", $port)
    $client.Close()
    Write-Host "✓ Maya command port $port is OPEN" -ForegroundColor Green
    
    # Run the test
    Write-Host ""
    Write-Host "Running lazy loading tests in Maya..." -ForegroundColor Cyan
    python o:\Cloud\Code\_scripts\test_maya_lazy_loading.py
    
} catch {
    Write-Host "❌ Maya command port $port is CLOSED" -ForegroundColor Red
    Write-Host ""
    Write-Host "To open the port, run this in Maya Script Editor (Python):" -ForegroundColor Yellow
    Write-Host "    import mayatk" -ForegroundColor White
    Write-Host "    mayatk.openPorts(python=':7002')" -ForegroundColor White
    Write-Host ""
    Write-Host "Then re-run this script." -ForegroundColor Yellow
    Write-Host ""
}
