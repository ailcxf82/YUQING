$body = @{
    target_type = "theme"
    keyword = "test"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v2/pipeline/task/create" -Method Post -Body $body -ContentType "application/json"
