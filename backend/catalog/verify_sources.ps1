param(
    [string]$Manifest = "$PSScriptRoot/required-sources.json",
    [string]$Report = "$PSScriptRoot/required-sources-verification.json",
    [string]$Python = "$PSScriptRoot/../.venv/Scripts/python.exe"
)
$ErrorActionPreference = 'Stop'
$registry = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
$allowedHosts = @('docs.python.org', 'www.typescriptlang.org', 'react.dev', 'nextjs.org',
    'tailwindcss.com', 'fastapi.tiangolo.com', 'pydantic.dev', 'docs.sqlalchemy.org',
    'docs.langchain.com', 'huggingface.co', 'docs.vllm.ai', 'www.postgresql.org',
    'github.com', 'qdrant.tech', 'redis.io', 'docs.docker.com', 'docs.github.com',
    'developer.hashicorp.com', 'docs.aws.amazon.com', 'opentelemetry.io',
    'prometheus.io', 'grafana.com', 'langfuse.com', 'docs.pytest.org', 'playwright.dev', 'raw.githubusercontent.com')
$pages = foreach ($entry in $registry.entries) {
    foreach ($page in $entry.pages) {
        $uri = [Uri]$page.url
        if (!$uri.IsAbsoluteUri -or $uri.Scheme -ne 'https' -or $uri.Host -notin $allowedHosts -or
            $uri.UserInfo -or $uri.Query -or $uri.Fragment -or !$uri.IsDefaultPort -or
            $uri.GetLeftPart([UriPartial]::Authority) -ne $page.origin -or
            $uri.AbsolutePath -ne $page.path -or !$page.url.StartsWith($entry.publisher_root)) {
            throw "Unbounded publisher URL in $($entry.id)"
        }
        [pscustomobject]@{entry_id=$entry.id; url=$page.url; origin=$page.origin}
    }
}
# This review-time verifier uses native TLS trust, not the production pinned-IP fetcher.
$lastRequest = @{}
function Get-BoundedResponse([string]$Url, [int]$MaxBytes, [int]$Delay = 1) {
    $hostName = ([Uri]$Url).Host
    if ($lastRequest.ContainsKey($hostName)) {
        $remaining = $Delay - ([DateTime]::UtcNow - $lastRequest[$hostName]).TotalSeconds
        if ($remaining -gt 0) { Start-Sleep -Milliseconds ([int][Math]::Ceiling($remaining * 1000)) }
    }
    $lastRequest[$hostName] = [DateTime]::UtcNow
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(10)
    $deadline = [Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(10))
    $client.DefaultRequestHeaders.UserAgent.ParseAdd('DocWeave/0.1')
    $client.DefaultRequestHeaders.AcceptEncoding.ParseAdd('identity')
    $response = $null
    $stream = $null
    $body = [System.IO.MemoryStream]::new()
    try {
        $response = $client.GetAsync($Url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead, $deadline.Token).GetAwaiter().GetResult()
        if ($response.Content.Headers.ContentEncoding.Count -gt 0 -and 'identity' -notin $response.Content.Headers.ContentEncoding) {
            throw 'Compressed response is unsupported'
        }
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $buffer = [byte[]]::new(8192)
        while (($count = $stream.ReadAsync($buffer, 0, $buffer.Length, $deadline.Token).GetAwaiter().GetResult()) -gt 0) {
            if ($body.Length + $count -gt $MaxBytes) { throw 'Response exceeds byte bound' }
            $body.Write($buffer, 0, $count)
        }
        $bytes = $body.ToArray()
        return [pscustomobject]@{
            status=[int]$response.StatusCode; mime=$response.Content.Headers.ContentType.MediaType
            body=$bytes; bytes=$bytes.Length; location=[string]$response.Headers.Location
            sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
            etag=[string]$response.Headers.ETag; last_modified=[string]$response.Content.Headers.LastModified
        }
    } finally {
        if ($stream) { $stream.Dispose() }
        if ($response) { $response.Dispose() }
        $body.Dispose(); $client.Dispose(); $handler.Dispose(); $deadline.Dispose()
    }
}
$robots = @(foreach ($origin in ($pages.origin | Sort-Object -Unique)) {
    $policy = [ordered]@{origin=$origin; url="$origin/robots.txt"; checked_at=[DateTime]::UtcNow.ToString('o')}
    try {
        $response = Get-BoundedResponse "$origin/robots.txt" 262144
        $policy.status = $response.status
        $policy.mime = $response.mime
        $policy.bytes = $response.bytes
        $policy.sha256 = $response.sha256
        if ($response.status -eq 200) { $policy.body_base64 = [Convert]::ToBase64String($response.body) }
        $policy.location = $response.location
    } catch { $policy.error = $_.Exception.Message }
    [pscustomobject]$policy
})
$decisionsPath = "$Report.robots-tmp.json"
try {
    @{robots=$robots; receipts=$pages} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $decisionsPath -Encoding utf8NoBOM
    & $Python "$PSScriptRoot/evaluate_robots.py" $decisionsPath
    if ($LASTEXITCODE -ne 0) { throw 'Robots policy evaluation failed' }
    $decisions = (Get-Content -LiteralPath $decisionsPath -Raw | ConvertFrom-Json).receipts
} finally { Remove-Item -LiteralPath $decisionsPath -ErrorAction SilentlyContinue }
$receipts = @(foreach ($page in $decisions) {
    $receipt = [ordered]@{entry_id=$page.entry_id; url=$page.url; checked_at=[DateTime]::UtcNow.ToString('o'); outcome='failed'; robots=$page.robots}
    try {
        if (!$page.robots.can_fetch) { throw $page.robots.reason }
        $response = Get-BoundedResponse $page.url 2097152 $page.robots.crawl_delay
        $receipt.status = $response.status
        if ($receipt.status -ne 200) { throw "Expected 200; received $($receipt.status); redirect=$($response.location)" }
        $mime = $response.mime
        if ($mime -notin @('text/html', 'text/plain', 'text/markdown')) { throw "Unsupported MIME: $mime" }
        $text = [Text.Encoding]::UTF8.GetString($response.body)
        $title = [regex]::Match($text, '(?is)<title[^>]*>(.*?)</title>').Groups[1].Value
        if ($mime -ne 'text/html') {
            $title = [regex]::Match($text, '(?m)^([^\r\n]+)\r?\n[=]{3,}\s*$').Groups[1].Value
            if (!$title) { $title = [regex]::Match($text, '(?m)^title:\s*["'']?([^"''\r\n]+)').Groups[1].Value }
        }
        if ($text -match '(?is)<meta[^>]+http-equiv\s*=\s*["'']?refresh') {
            throw 'HTML refresh redirect is not a documentation body'
        }
        if ($mime -eq 'text/html' -and (!$title -or $title -match '(?i)404|page not found|access denied|just a moment')) {
            throw "Missing or error page title: $title"
        }
        $receipt.outcome = 'verified'
        $receipt.mime = $mime
        $receipt.bytes = $response.bytes
        $receipt.sha256 = $response.sha256
        $receipt.title = [Net.WebUtility]::HtmlDecode(($title -replace '\s+', ' ').Trim())
        $heading = [regex]::Match($text, '(?is)<h1[^>]*>(.*?)</h1>').Groups[1].Value
        if ($mime -ne 'text/html') { $heading = $title }
        $receipt.first_heading = [Net.WebUtility]::HtmlDecode(($heading -replace '<[^>]+>', '' -replace '\s+', ' ').Trim())
        $receipt.etag = $response.etag
        $receipt.last_modified = $response.last_modified
        $parseMedia = $mime
        if ($mime -ne 'text/html' -and ([Uri]$page.url).AbsolutePath -match '\.(md|markdown)$') { $parseMedia = 'text/markdown' }
        $receipt.parser_media_type = $parseMedia
        $parseRequest = @{body_base64=[Convert]::ToBase64String($response.body); mime=$parseMedia} | ConvertTo-Json -Compress
        $parseResult = $parseRequest | & $Python "$PSScriptRoot/parse_page.py"
        if ($LASTEXITCODE -ne 0) { throw 'Application parser failed' }
        $receipt.parse = $parseResult | ConvertFrom-Json
        if ($receipt.parse.outcome -ne 'verified') { throw "Parser: $($receipt.parse.error)" }
    } catch { $receipt.outcome = 'failed'; $receipt.error = $_.Exception.Message }
    [pscustomobject]$receipt
})
$manifestBytes = [Text.Encoding]::UTF8.GetBytes((Get-Content -LiteralPath $Manifest -Raw).Replace("`r`n", "`n"))
$result = [ordered]@{
    schema_version=1
    manifest_sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($manifestBytes)).ToLowerInvariant()
    manifest_hash_encoding='UTF-8 with CRLF normalized to LF; publisher body hashes have no normalization'
    checked_at=[DateTime]::UtcNow.ToString('o')
    method='DocWeave/0.1 HTTPS GET; redirects refused; 10 second whole-response deadline; >=1 second between requests per host (honoring supported robots crawl delays); 2 MiB/page and 256 KiB/robots cap; SHA256 of raw response bodies'
    robots=$robots
    robots_agent='DocWeave/0.1'
    robots_parser='Python standard-library urllib.robotparser.RobotFileParser, matching ingestion status and crawl-delay policy'
    receipts=@($receipts | Sort-Object entry_id, url)
}
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Report -Encoding utf8NoBOM
$failed = @($receipts | Where-Object outcome -ne 'verified')
Write-Output "$($receipts.Count - $failed.Count)/$($receipts.Count) bounded pages verified; report: $Report"
$failed | Select-Object entry_id, url, error | Format-Table -Wrap
if ($failed.Count) { exit 1 }
