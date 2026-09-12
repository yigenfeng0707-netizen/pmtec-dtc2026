$tests = @(
    "test_p6.py", "test_p7.py", "test_p8.py", "test_p9.py", "test_p10.py",
    "test_p11.py", "test_p12_1_obs.py", "test_p12_3_websocket.py", "test_p12_final.py"
)
$py = "D:/miniconda3/envs/pmtec-xpu/python.exe"
Set-Location "d:/APPs/数字孪生挑战赛/pmtec_system"
$totalPass = 0; $totalFail = 0; $failedFiles = @()
foreach ($t in $tests) {
    $out = & $py $t 2>&1
    $exit = $LASTEXITCODE
    $summary = ($out | Select-String "通过 / |passed|PASS=" | Select-Object -Last 1).Line
    Write-Output ("== {0}  exit={1}  {2}" -f $t, $exit, $summary.Trim())
    if ($exit -ne 0) { $failedFiles += $t }
}
Write-Output "---"
if ($failedFiles.Count -eq 0) { Write-Output "REGRESSION: ALL OK" } else { Write-Output ("REGRESSION FAILED: " + ($failedFiles -join ", ")) }
