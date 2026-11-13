param(
    [string]$TargetPath,
    [string]$Sentence
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient

# 1. Start Notepad with target path
$proc = Start-Process notepad.exe -ArgumentList $TargetPath -PassThru
Start-Sleep -Seconds 2

# 2. If 'create file' prompt appears, send Enter
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Seconds 1

# 3. Send test sentence
[System.Windows.Forms.SendKeys]::SendWait($Sentence)
Start-Sleep -Seconds 1

# 4. Save with Ctrl+S
[System.Windows.Forms.SendKeys]::SendWait('^s')
Start-Sleep -Seconds 2

# 5. Close window
$proc.CloseMainWindow()
Start-Sleep -Seconds 1
if (-not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
}
Write-Output "FINISHED_NOTEPAD_OPERATOR"

