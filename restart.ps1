# Restart Smoothie Registration Application Script
Write-Host "Stopping Email Subscription application..." -ForegroundColor Yellow

# Fixed: Moved ErrorAction to Get-Process so it doesn't crash when Python is already stopped
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

Start-Sleep -Seconds 2

Write-Host "Starting Email Subscription application..." -ForegroundColor Green

uv run main.py

Write-Host "Email Subscription application restarted successfully." -ForegroundColor Green
