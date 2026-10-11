$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'release-manifest.json') -Raw | ConvertFrom-Json
foreach ($part in $manifest.parts) {
    $path = Join-Path $PSScriptRoot $part.file
    if (!(Test-Path -LiteralPath $path)) { throw "缺少分卷：$($part.file)" }
    Write-Host "校验 $($part.file)"
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $part.sha256) { throw "分卷损坏：$($part.file)，请重新下载" }
}
$target = Join-Path $PSScriptRoot $manifest.archive
if ((Test-Path -LiteralPath $target) -and ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -eq $manifest.sha256)) {
    Write-Host 'ZIP 已存在且校验通过，可直接解压。'
    exit 0
}
$output = [IO.File]::Create($target)
try {
    foreach ($part in $manifest.parts) {
        $inputStream = [IO.File]::OpenRead((Join-Path $PSScriptRoot $part.file))
        try { $inputStream.CopyTo($output) } finally { $inputStream.Dispose() }
    }
} finally { $output.Dispose() }
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.sha256) { throw '合并后的 ZIP 校验失败，请勿使用。' }
Write-Host "合并并校验成功：$target。请解压后启动数字人工作台.exe。"
