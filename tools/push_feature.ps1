<#
Push a branch of daboodah-oss/iu-qb-report from this PC.  Never pushes main.
Authentication: Git Credential Manager (Windows Credential Manager).  No token is read from or written to any file.

  powershell -ExecutionPolicy Bypass -File push_feature.ps1 [-Branch feature/x] [-Patch C:\path\changes.patch] [-Run]

First push on a new PC: Git shows a GitHub sign-in window.  Choose "Token" and paste the fine-grained PAT
(from LastPass).  Git Credential Manager stores it; later pushes do not prompt.
-Patch  applies a patch file (git am) when the branch does not exist on GitHub yet.
-Run    starts the "Update report" workflow on the branch (it commits only to that branch; Pages serves main).
#>
param(
  [string]$Branch = "feature/cignetti-qbs",
  [string]$Patch = "",
  [string]$Clone = "$env:USERPROFILE\github\iu-qb-report",
  [switch]$Run
)
$ErrorActionPreference = "Stop"
$Repo = "daboodah-oss/iu-qb-report"
function Need($ok, $msg) { if (-not $ok) { Write-Host "STOP: $msg" -ForegroundColor Red; exit 1 } }

Need ($Branch -ne "main") "this script never pushes main"
git --version | Out-Null
$helper = git config --get credential.helper
Need ($helper -match "manager") "credential.helper is '$helper'.  Install Git for Windows (includes Git Credential Manager) or run: git config --global credential.helper manager"

if (-not (Test-Path "$Clone\.git")) {
  New-Item -ItemType Directory -Force (Split-Path $Clone) | Out-Null
  git clone "https://github.com/$Repo.git" $Clone
}
Set-Location $Clone
if (-not (git config user.email)) { git config user.name "Jeff Bandera"; git config user.email "daboodah-oss@users.noreply.github.com" }
git fetch -q origin

if (git ls-remote --heads origin $Branch) {
  git checkout -q -B $Branch "origin/$Branch"
} else {
  git checkout -q -B $Branch origin/main
  if ($Patch) { git am $Patch; Need ($LASTEXITCODE -eq 0) "patch did not apply (git am --abort to reset)" }
}

$changed = git diff --name-only origin/main...HEAD
Need (-not ($changed -contains "CNAME")) "CNAME is changed on this branch"
$leak = git grep -nE "github_pat_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}" HEAD
Need (-not $leak) "token-like text found in the tree"

git push -u origin $Branch
Need ($LASTEXITCODE -eq 0) "push failed"
Write-Host "Remote now has:" ; git ls-remote origin "refs/heads/$Branch"

if ($Run) {
  # Read the stored credential into memory only, for one API call.  Never printed or saved.
  $fill = "protocol=https`nhost=github.com`n`n" | git credential fill
  $pw = ($fill | Where-Object { $_ -like "password=*" }) -replace "^password=", ""
  Need ($pw) "no stored GitHub credential; push once first"
  try {
    Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Repo/actions/workflows/update.yml/dispatches" `
      -Headers @{ Authorization = "Bearer $pw"; Accept = "application/vnd.github+json" } `
      -Body (@{ ref = $Branch } | ConvertTo-Json) | Out-Null
    Write-Host "Started 'Update report' on $Branch.  Results: https://github.com/$Repo/actions"
  } finally { Remove-Variable pw, fill -ErrorAction SilentlyContinue }
}
