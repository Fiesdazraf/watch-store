Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Go to project root
Set-Location -Path "$PSScriptRoot\.."

Write-Output "Freezing all installed packages..."
pip freeze | Out-File -Encoding utf8 requirements\full.txt

Write-Output "Splitting into base.txt and dev.txt..."
$base = "^(Django|asgiref|dj-database-url|pillow|sqlparse|tzdata|whitenoise)"

# Create base.txt
Get-Content requirements\full.txt | Select-String -Pattern $base | ForEach-Object { $_.Line } | Out-File -Encoding utf8 requirements\base.txt

# Create dev.txt
" -r base.txt" | Out-File -Encoding utf8 requirements\dev.txt
Get-Content requirements\full.txt | Select-String -NotMatch -Pattern $base | ForEach-Object { $_.Line } | Out-File -Append -Encoding utf8 requirements\dev.txt

Write-Output "Done. Updated requirements\base.txt and requirements\dev.txt"
