param(
    [switch]$Update
)

$submodulePath = "vendor/ffxiv-datamining"

if (-not (Test-Path $submodulePath)) {
    Write-Host "Submodule not found at $submodulePath"
    Write-Host "To add it run:`n  git submodule add https://github.com/xivapi/ffxiv-datamining $submodulePath`n  git submodule update --init --recursive"
    exit 1
}

Push-Location $submodulePath

# attempt to fetch remote
git fetch origin 2>$null

$local = (git rev-parse HEAD).Trim()

$ls = (git ls-remote origin HEAD 2>$null)
if ($ls) {
    $remote = $ls.Split("`t")[0].Trim()
} else {
    try {
        $remote = (git rev-parse origin/HEAD).Trim()
    } catch {
        $remote = ""
    }
}

if ([string]::IsNullOrEmpty($remote)) {
    Write-Host "Unable to determine remote HEAD. Abort."
    Pop-Location
    exit 2
}

if ($local -ne $remote) {
    Write-Host "Update available: local=$local remote=$remote"
    if ($Update) {
        git pull --ff-only
        Write-Host "Submodule updated to $(git rev-parse HEAD)"
    } else {
        Write-Host "Run with -Update to pull latest changes."
    }
} else {
    Write-Host "Submodule is up-to-date."
}

Pop-Location
