<#
Start the "Update report" workflow on demand.  Uses the github.com credential stored by Git Credential
Manager (fetched with `git credential fill`, held in memory for one API call, never printed or saved).

  powershell -ExecutionPolicy Bypass -File run_workflow.ps1 [-Ref main] [-SaveRaw]

-Ref      branch to run on (default main; a run on another branch commits only to that branch)
-SaveRaw  also save the raw source pages to raw/ for debugging
Without the PC: GitHub app or website, Actions tab, "Update report", "Run workflow".
#>
param([string]$Ref = "main", [switch]$SaveRaw)
$ErrorActionPreference = "Stop"
$Repo = "daboodah-oss/iu-qb-report"
$env:GCM_INTERACTIVE = "never"; $env:GIT_TERMINAL_PROMPT = "0"
$fill = "protocol=https`nhost=github.com`n`n" | git credential fill
$pw = ($fill | Where-Object { $_ -like "password=*" }) -replace "^password=", ""
if (-not $pw) { Write-Host "STOP: no stored GitHub credential.  Push once with push_feature.ps1 first." -ForegroundColor Red; exit 1 }
try {
  $body = @{ ref = $Ref; inputs = @{ save_raw = [bool]$SaveRaw } } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Repo/actions/workflows/update.yml/dispatches" `
    -Headers @{ Authorization = "Bearer $pw"; Accept = "application/vnd.github+json" } -Body $body | Out-Null
  Write-Host "Started 'Update report' on $Ref$(if ($SaveRaw) {' (saving raw pages)'}).  Results: https://github.com/$Repo/actions"
} finally { Remove-Variable pw, fill -ErrorAction SilentlyContinue }
