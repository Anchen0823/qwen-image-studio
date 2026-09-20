$ErrorActionPreference = 'Stop'
$studioSkillSource = Join-Path $PSScriptRoot 'skills\qwen-image-local'
$studioSkillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex\skills' }
$studioSkillTarget = Join-Path $studioSkillRoot 'qwen-image-local'
New-Item -ItemType Directory -Path $studioSkillTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $studioSkillSource 'SKILL.md') -Destination $studioSkillTarget -Force
foreach ($studioSkillSubdir in @('agents', 'scripts')) {
    $studioSkillSubtarget = Join-Path $studioSkillTarget $studioSkillSubdir
    New-Item -ItemType Directory -Path $studioSkillSubtarget -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $studioSkillSource $studioSkillSubdir) -File | Copy-Item -Destination $studioSkillSubtarget -Force
}
Write-Output "Installed: $studioSkillTarget"
