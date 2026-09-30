Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n); }
"@
$w = Get-Process freecad -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -ne '' } | Select-Object -First 1
if ($w) {
  [W]::ShowWindow($w.MainWindowHandle, 9) | Out-Null
  Start-Sleep -Milliseconds 150
  [W]::SetForegroundWindow($w.MainWindowHandle) | Out-Null
  Write-Output "Activated FreeCAD"
} else {
  Write-Output "No FreeCAD window found"
}
