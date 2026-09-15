param([string]$Runtime = $(if ($env:ALEXANDRIA_RUNTIME_DIR) { $env:ALEXANDRIA_RUNTIME_DIR } else { Join-Path $env:USERPROFILE '.alexandria\runtime' }))
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
$log = Join-Path $Runtime 'install.log'
$channels = @('https://conda.anaconda.org/conda-forge', 'https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge')
if ($env:ALEXANDRIA_MIRROR_FIRST -eq '1') { [array]::Reverse($channels) }
$mamba = Join-Path $Runtime 'Library\bin\micromamba.exe'
function Invoke-Native([string]$Program, [string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    & $Program @Arguments >> $log 2>&1
    return $LASTEXITCODE
}
try {
    if (-not (Test-Path $mamba)) {
        $archive = Join-Path $Runtime 'micromamba.tar.bz2'
        $downloaded = $false
        foreach ($channel in $channels) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri "$channel/win-64/micromamba-2.9.0-0.tar.bz2" -OutFile $archive -TimeoutSec 180
                if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -ne '97a336f4ab794bd96a6a4da5e6ed63e75a1d31830414a182419b23d3b36f3fe0') { throw 'Download checksum mismatch.' }
                $downloaded = $true
                break
            } catch { $_ | Out-File -Append $log }
        }
        if (-not $downloaded) { throw 'Could not download the installer.' }
        $code = Invoke-Native -Program 'tar' -Arguments @('-xjf', $archive, '-C', $Runtime, 'Library/bin/micromamba.exe')
        if ($code -ne 0) { throw 'Could not unpack the installer.' }
        Remove-Item $archive
    }
    $env:MAMBA_ROOT_PREFIX = Join-Path $Runtime 'mamba'
    $prefix = Join-Path $Runtime 'env'
    $action = if (Test-Path (Join-Path $prefix 'conda-meta\history')) { 'install' } else { 'create' }
    $installed = $false
    foreach ($channel in $channels) {
        $code = Invoke-Native -Program $mamba -Arguments @('--no-rc', $action, '--yes', '--prefix', $prefix, '--override-channels', '--channel', $channel, 'python=3.12', 'pip', 'pango', 'fontconfig')
        if ($code -eq 0) { $installed = $true; break }
    }
    if (-not $installed) { throw 'Could not create the runtime.' }
    $code = Invoke-Native -Program $mamba -Arguments @('--no-rc', 'run', '--prefix', $prefix, 'python', (Join-Path $PSScriptRoot 'install_runtime.py'), '--runtime', $Runtime)
    if ($code -ne 0) { throw 'Runtime verification failed.' }
    Write-Output "Installed and verified. Runtime: $Runtime (launcher: $Runtime\bin\python.cmd)"
} catch {
    $_ | Out-File -Append $log
    Write-Error "Installation failed; see $log"
    exit 1
}
