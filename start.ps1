param(
    [ValidateSet('start', 'install', 'test', 'diagnose', 'login')][string]$Action = 'start',
    [ValidateSet('msedge', 'chrome', 'chromium')][string]$Browser = 'msedge'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $candidates = @($env:JW_SWU_PYTHON, (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'))
        foreach ($command in @('python', 'py')) {
            $found = Get-Command $command -ErrorAction SilentlyContinue
            if ($found) { $candidates += $found.Source }
        }
        $python = $null
        foreach ($candidate in $candidates) {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null
                if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
            }
        }
        if (-not $python) { throw '请安装 Python 3.10+，或通过 JW_SWU_PYTHON 指定 python.exe。' }
        & $python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 虚拟环境创建失败。' }
    }
    $requirements = if ($Action -eq 'test') { 'requirements-dev.txt' } else { 'requirements.txt' }
    $stamp = Join-Path $PSScriptRoot ('.venv\' + $requirements + '.sha256')
    $hash = (Get-FileHash requirements.txt).Hash + (Get-FileHash $requirements).Hash
    if ($Action -eq 'install' -or -not (Test-Path $stamp) -or (Get-Content -Raw $stamp).Trim() -ne $hash) {
        & $venvPython -m pip install -r $requirements
        if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络后重新启动。' }
        Set-Content -LiteralPath $stamp -Value $hash
    }
    if ($Browser -eq 'chromium' -or $Action -eq 'test') {
        # Probe an existing installation before touching the shared download cache.
        # This also allows local tests to run offline after the first installation.
        & $venvPython -c 'from BrowserSession import browser_available; raise SystemExit(0 if browser_available() else 1)'
        if ($LASTEXITCODE -ne 0) {
            & $venvPython -m playwright install chromium
            if ($LASTEXITCODE -ne 0) { throw 'Chromium 安装失败，请检查网络。' }
        }
    }
    if ($Action -eq 'install') { Write-Output 'INSTALL_OK'; exit 0 }
    if ($Action -eq 'test') {
        $runDir = Join-Path $PSScriptRoot ('.venv\test-runs\' + [Guid]::NewGuid().ToString('N'))
        $testRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.venv\test-runs')) + [IO.Path]::DirectorySeparatorChar
        if (-not ([IO.Path]::GetFullPath($runDir)).StartsWith($testRoot, [StringComparison]::OrdinalIgnoreCase)) { throw '测试目录校验失败。' }
        New-Item -ItemType Directory -Path $runDir -Force | Out-Null
        $env:COVERAGE_FILE = Join-Path $runDir '.coverage'
        & $venvPython -m pytest -q -p no:cacheprovider --basetemp (Join-Path $runDir 'tmp') --cov=BrowserSession --cov=Login --cov=Course_Selection --cov-report=term-missing --cov-fail-under=90
    } else {
        $cli = @('Course_Selection.py', '--browser', $Browser)
        if ($Action -eq 'diagnose') { $cli += '--diagnose' }
        if ($Action -eq 'login') { $cli += '--login-only' }
        & $venvPython @cli
    }
    exit $LASTEXITCODE
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
