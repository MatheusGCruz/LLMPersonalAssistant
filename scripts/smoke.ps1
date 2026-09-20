$ErrorActionPreference = "Stop"
$base = if ($env:LLMPA_PORT) { "http://localhost:$env:LLMPA_PORT" } else { "http://localhost:8000" }

Write-Host "== health =="
Invoke-RestMethod -Uri "$base/health" | ConvertTo-Json -Depth 4

Write-Host "`n== assistant: roll 2d6 (pattern = direct tool call) =="
$body = @{ message = "roll 2d6" } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/assistant" -Method Post -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6

Write-Host "`n== assistant: calc 121*17 =="
$body = @{ message = "calc 121 * 17" } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/assistant" -Method Post -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6

Write-Host "`n== chat: generic question through local model with tools =="
$body = @{ messages = @(@{ role = "user"; content = "What is the time, in one short sentence?" }) } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "$base/chat" -Method Post -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6