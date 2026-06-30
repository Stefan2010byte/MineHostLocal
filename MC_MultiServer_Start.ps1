# ============================================================
#  MC_MultiServer_Start.ps1
#  Backup + 3 Minecraft-Instanzen mit RAM & CPU-Affinity
# ============================================================

# ── HIER ANPASSEN ──────────────────────────────────────────
$JavaExe     = "java"   # oder z.B. "C:\Program Files\Java\jdk-21\bin\java.exe"

$Server1_Dir = "C:\MC_Server\Velocity"        # Proxy/Velocity
$Server2_Dir = "C:\MC_Server\Lobby"           # Lobby
$Server3_Dir = "C:\MC_Server\Game"            # Game-Server

$Server1_Jar = "velocity.jar"
$Server2_Jar = "server.jar"
$Server3_Jar = "server.jar"

# RAM
$Server1_Ram = "2G"    # Velocity
$Server2_Ram = "6G"    # Lobby
$Server3_Ram = "12G"   # Game

# CPU-KERNE (0-basiert) ─ HIER DEINE KERN-AUFTEILUNG EINTRAGEN
# Beispiel für 6 physische Kerne / 12 logische (Hyperthreading):
#   Velocity → Kern 0-1       (2 Threads)
#   Lobby    → Kern 2-5       (4 Threads)
#   Game     → Kern 6-11      (6 Threads)
$Server1_Cores = @(0, 1)
$Server2_Cores = @(2, 3, 4, 5)
$Server3_Cores = @(6, 7, 8, 9, 10, 11)

# Backup-Ziel
$BackupSource = $Server2_Dir
$BackupBase   = "E:\Minecraft_Backups"
# ── ENDE KONFIGURATION ──────────────────────────────────────


function Get-AffinityMask([int[]]$Cores) {
    $mask = 0
    foreach ($c in $Cores) { $mask = $mask -bor (1 -shl $c) }
    return $mask
}

# SCHRITT 1: Backup
$ts     = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$BakDir = "$BackupBase\Backup_$ts"
Write-Host "=== BACKUP ===" -ForegroundColor Cyan
Write-Host "Quelle : $BackupSource"
Write-Host "Ziel   : $BakDir"

if (-not (Test-Path $BackupBase)) { New-Item -ItemType Directory -Path $BackupBase | Out-Null }
Copy-Item -Path $BackupSource -Destination $BakDir -Recurse -Force
Write-Host "Backup fertig!" -ForegroundColor Green

# SCHRITT 2: Server starten
Write-Host "`n=== SERVER STARTEN ===" -ForegroundColor Cyan

function Start-MCServer {
    param(
        [string]$Name,
        [string]$Dir,
        [string]$Jar,
        [string]$Ram,
        [int[]] $Cores
    )
    $mask    = Get-AffinityMask $Cores
    $jvmArgs = "-Xms$Ram -Xmx$Ram -jar `"$Jar`" --nogui"
    Write-Host "Starte $Name | RAM: $Ram | Kerne: $($Cores -join ',') | Maske: $mask"

    $proc = Start-Process -FilePath $JavaExe -ArgumentList $jvmArgs `
                          -WorkingDirectory $Dir -PassThru -WindowStyle Normal

    Start-Sleep -Milliseconds 800
    try {
        $proc.ProcessorAffinity = [IntPtr]$mask
        Write-Host "  OK $Name (PID $($proc.Id)  Affinity 0x$('{0:X}' -f $mask))" -ForegroundColor Green
    } catch {
        Write-Host "  WARN $Name gestartet, Affinity fehlgeschlagen: $_" -ForegroundColor Yellow
    }
    return $proc
}

$p1 = Start-MCServer -Name "Velocity" -Dir $Server1_Dir -Jar $Server1_Jar -Ram $Server1_Ram -Cores $Server1_Cores
Start-Sleep -Seconds 3
$p2 = Start-MCServer -Name "Lobby"    -Dir $Server2_Dir -Jar $Server2_Jar -Ram $Server2_Ram -Cores $Server2_Cores
Start-Sleep -Seconds 3
$p3 = Start-MCServer -Name "Game"     -Dir $Server3_Dir -Jar $Server3_Jar -Ram $Server3_Ram -Cores $Server3_Cores

Write-Host "`n=== FERTIG ===" -ForegroundColor Green
Write-Host "Velocity  PID $($p1.Id)"
Write-Host "Lobby     PID $($p2.Id)"
Write-Host "Game      PID $($p3.Id)"
Read-Host "`nEnter zum Schliessen"
