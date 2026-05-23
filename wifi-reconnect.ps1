$logFile = "C:\Project\wifi-reconnect.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Test against 2 hosts with 2 pings each to avoid false positives
$connected = (Test-Connection -ComputerName 8.8.8.8 -Count 2 -Quiet) -or `
             (Test-Connection -ComputerName 1.1.1.1 -Count 2 -Quiet)

if (-not $connected) {
    "$timestamp - No internet detected. Attempting reconnect..." | Out-File -Append $logFile

    # Get current WiFi profile dynamically
    $ssid = (netsh wlan show interfaces | Select-String "^\s+SSID\s+:" | Select-String -NotMatch "BSSID") -replace ".*:\s+", ""
    $ssid = $ssid.Trim()

    if ($ssid) {
        netsh wlan connect name="$ssid"
        Start-Sleep -Seconds 12

        $recheck = (Test-Connection -ComputerName 8.8.8.8 -Count 2 -Quiet) -or `
                   (Test-Connection -ComputerName 1.1.1.1 -Count 2 -Quiet)

        if ($recheck) {
            "$timestamp - Reconnect successful." | Out-File -Append $logFile
        } else {
            "$timestamp - Reconnect FAILED." | Out-File -Append $logFile
        }
    } else {
        "$timestamp - No WiFi profile found, cannot reconnect." | Out-File -Append $logFile
    }
}
