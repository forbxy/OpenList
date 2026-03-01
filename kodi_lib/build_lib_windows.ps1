# Set stop on error
$ErrorActionPreference = "Stop"

# Get script directory and move there
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Fetching frontend assets..."
if (Test-Path "fetch_frontend.py") {
    python fetch_frontend.py
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to fetch frontend assets."
        exit 1
    }
}

Write-Host "Checking for gcc..."
if (-not (Get-Command gcc -ErrorAction SilentlyContinue)) {
    Write-Error "Error: gcc not found in PATH."
    Write-Host "Please install MinGW-w64 or another GCC compiler for Windows."
    Write-Host "You can download it from https://winlibs.com/"
    Read-Host "Press Enter to exit"
    exit 1
}

# Create output directory if it doesn't exist
if (-not (Test-Path "output")) {
    New-Item -ItemType Directory -Force -Path "output" | Out-Null
}

# Get the latest tag for versioning
try {
    # Check if we are in a git repository or if git is available
    $fullTag = git describe --tags --abbrev=0
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not determine git tag. Using 'dev' as version."
        $version = "dev"
    } else {
        # Strip leading 'v' if present (e.g., v1.2.3 -> 1.2.3)
        $fullTag = $fullTag.Trim()
        if ($fullTag.StartsWith("v")) {
            $version = $fullTag.Substring(1)
        } else {
            $version = $fullTag
        }
    }
} catch {
    Write-Warning "Git error. Using 'dev' as version."
    $version = "dev"
}

# Determine architecture for filename
$arch = "x86_64"
if ($env:GOARCH -eq "386") {
    $arch = "i686"
} elseif ($env:GOARCH -eq "arm64") {
    $arch = "aarch64"
}
# Default to x86_64 if not set, as most devs are on 64-bit windows

$libName = "libopenlist-$version-windows-$arch.dll"
$tempLibName = "libopenlist.dll"

Write-Host "Building $libName..."

# Build command - build to temp name first to avoid mingw/ld confusion with dots in filename
go build -buildmode=c-shared -o "output\$tempLibName" lib_openlist.go
if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed."
    exit 1
}

# Rename/Move to final name
Move-Item -Path "output\$tempLibName" -Destination "output\$libName" -Force
if (Test-Path "output\$tempLibName") { Remove-Item "output\$tempLibName" }

Write-Host "Build successful."
Write-Host "Copying to addon directory..."

# Define destination directory (relative to script location)
$addonLibDir = Join-Path $scriptDir "..\..\plugin.service.forbxy.openlist\lib"

# Create destination directory if it doesn't exist
if (-not (Test-Path $addonLibDir)) {
    New-Item -ItemType Directory -Force -Path $addonLibDir | Out-Null
}

# Copy the DLL
try {
    Copy-Item "output\$libName" -Destination $addonLibDir -Force
    Write-Host "Copied $libName to $addonLibDir"
} catch {
    Write-Error "Failed to copy DLL: $_"
    exit 1
}

Write-Host "Done! Restart Kodi to test."
