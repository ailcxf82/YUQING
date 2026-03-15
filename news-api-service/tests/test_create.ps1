$body = @{
    target_type = "theme"
    keyword = "test keyword"
    time_range = "7days"
    analysis_depth = "standard"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/api/v2/pipeline/task/create" -Method Post -Body $body -ContentType "application/json"
