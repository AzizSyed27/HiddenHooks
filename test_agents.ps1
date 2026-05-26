$base = "http://localhost:8000"
$tmp = "$env:TEMP\hh_body.json"

function Post($url, $json) {
    Set-Content -Path $tmp -Value $json -Encoding UTF8
    curl.exe -s -X POST $url -H "Content-Type: application/json" -d "@$tmp"
}

Write-Host "`n=== 422: invalid lat ===" -ForegroundColor Yellow
Post "$base/agents/trip-plan" '{"candidate_id": 1, "near_lat": 99.0, "near_lon": -79.26}' | python -m json.tool

Write-Host "`n=== 422: empty candidate_ids ===" -ForegroundColor Yellow
Post "$base/agents/rerank" '{"candidate_ids": [], "near_lat": 43.77, "near_lon": -79.26}' | python -m json.tool

Write-Host "`n=== 422: duplicate candidate_ids ===" -ForegroundColor Yellow
Post "$base/agents/rerank" '{"candidate_ids": [1, 1, 2], "near_lat": 43.77, "near_lon": -79.26}' | python -m json.tool

Write-Host "`n=== 404: unknown candidate ===" -ForegroundColor Yellow
Post "$base/agents/trip-plan" '{"candidate_id": 99999, "near_lat": 43.77, "near_lon": -79.26}' | python -m json.tool

Write-Host "`n=== Live trip-plan (candidate 1352497) ===" -ForegroundColor Cyan
Set-Content -Path $tmp -Value '{"candidate_id": 1352497, "near_lat": 43.77, "near_lon": -79.26}' -Encoding UTF8
curl.exe -s -X POST "$base/agents/trip-plan?debug=true" -H "Content-Type: application/json" -d "@$tmp" -o docs\sample_trip_plan_response.json
Write-Host "Saved to docs\sample_trip_plan_response.json"

Write-Host "`n=== Live rerank (1352497, 33647, 1) ===" -ForegroundColor Cyan
Set-Content -Path $tmp -Value '{"candidate_ids": [1352497, 33647, 1], "near_lat": 43.77, "near_lon": -79.26, "top_n": 5}' -Encoding UTF8
curl.exe -s -X POST "$base/agents/rerank?debug=true" -H "Content-Type: application/json" -d "@$tmp" -o docs\sample_rerank_response.json
Write-Host "Saved to docs\sample_rerank_response.json"

Remove-Item $tmp -ErrorAction SilentlyContinue