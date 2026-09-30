// PC doctor + gaming optimiser. diagnose() is read-only; optimise() makes a restore point, saves every
// previous value to pcdoctor-undo.json, then applies reversible tweaks only; undo() puts them all back.
// No Defender/Update changes, no elevation: anything needing admin (HAGS, restore point) is tried and reported.
const { execFileSync } = require('child_process');
const fs = require('fs'), path = require('path');

const ps = (script, env = {}) => execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script],
  { windowsHide: true, encoding: 'utf8', timeout: 120000, stdio: 'pipe', env: { ...process.env, ...env } }).trim();

const DIAG = String.raw`$ErrorActionPreference='SilentlyContinue'
$os=Get-CimInstance Win32_OperatingSystem
$r=[ordered]@{
 os="$($os.Caption) $($os.BuildNumber)"; uptimeH=[math]::Round(((Get-Date)-$os.LastBootUpTime).TotalHours,1)
 cpuLoad=(Get-CimInstance Win32_Processor|Measure-Object LoadPercentage -Average).Average
 ramUsedPct=[math]::Round(100-$os.FreePhysicalMemory/$os.TotalVisibleMemorySize*100)
 disks=@(Get-Volume|?{$_.DriveLetter -and $_.Size}|%{"$($_.DriveLetter): $([math]::Round($_.SizeRemaining/1GB))GB free of $([math]::Round($_.Size/1GB))GB ($([math]::Round($_.SizeRemaining/$_.Size*100))%)"})
 diskHealth=@(Get-PhysicalDisk|%{"$($_.FriendlyName): $($_.HealthStatus)"})
 temps=@(Get-CimInstance -Namespace root/wmi MSAcpi_ThermalZoneTemperature|%{"$([math]::Round($_.CurrentTemperature/10-273.15))C"}) + @(nvidia-smi --query-gpu=name,temperature.gpu --format=csv,noheader|%{"$_ C"})
 gpu=@(Get-CimInstance Win32_VideoController|%{"$($_.Name) driver $($_.DriverVersion) ($($_.DriverDate.ToString('yyyy-MM-dd')))"})
 badDevices=@(Get-CimInstance Win32_PnPEntity|?{$_.ConfigManagerErrorCode -ne 0}|%{"$($_.Name) (code $($_.ConfigManagerErrorCode))"})
 startup=@(Get-CimInstance Win32_StartupCommand|%{$_.Name})
 powerPlan=(powercfg /getactivescheme) -replace '.*\((.*)\).*','$1'
 errors24h=@(Get-WinEvent -FilterHashtable @{LogName='System','Application';Level=1,2;StartTime=(Get-Date).AddDays(-1)} -MaxEvents 500|Group-Object ProviderName|Sort Count -Desc|Select -First 6|%{"$($_.Name) x$($_.Count): $(($_.Group[0].Message -split [char]10)[0].Trim())"})
}
$r|ConvertTo-Json -Depth 3 -Compress`;

// HKCU tweaks (no admin). HAGS is HKLM and needs admin + reboot, so it's attempted and may be skipped.
// Game DVR background recording is left alone on purpose: he clips gameplay.
const TWEAKS = [
  ['Game Mode on', 'HKCU:\\Software\\Microsoft\\GameBar', 'AutoGameModeEnabled', 1],
  ['Transparency effects off', 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize', 'EnableTransparency', 0],
  ['Visual effects: best performance', 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects', 'VisualFXSetting', 2],
  ['Background apps off', 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications', 'GlobalUserDisabled', 1],
  ['Mouse acceleration off', 'HKCU:\\Control Panel\\Mouse', 'MouseSpeed', '0'],
  ['Mouse acceleration off', 'HKCU:\\Control Panel\\Mouse', 'MouseThreshold1', '0'],
  ['Mouse acceleration off', 'HKCU:\\Control Panel\\Mouse', 'MouseThreshold2', '0'],
  ['Hardware-accelerated GPU scheduling on (after reboot)', 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers', 'HwSchMode', 2],
].map(([label, p, name, value]) => ({ label, path: p, name, value }));

// Reads the old value (null = missing), writes the new one; per-item errors come back instead of throwing.
const REGSET = String.raw`$out=foreach($c in ($env:JV_REG|ConvertFrom-Json)){
 try{ $old=(Get-ItemProperty -Path $c.path -Name $c.name -EA Stop).($c.name) }catch{ $old=$null }
 try{
  if(-not(Test-Path $c.path)){ New-Item -Path $c.path -Force -EA Stop|Out-Null }
  if($c.value -eq $null){ Remove-ItemProperty -Path $c.path -Name $c.name -EA Stop }
  else{ $t=if($c.value -is [string]){'String'}else{'DWord'}; New-ItemProperty -Path $c.path -Name $c.name -Value $c.value -PropertyType $t -Force -EA Stop|Out-Null }
  [pscustomobject]@{path=$c.path;name=$c.name;old=$old;ok=$true}
 }catch{ [pscustomobject]@{path=$c.path;name=$c.name;old=$old;ok=$false;err=$_.Exception.Message} }
}
ConvertTo-Json @($out) -Compress`;
const regSet = changes => JSON.parse(ps(REGSET, { JV_REG: JSON.stringify(changes) }) || '[]');

const HIGH_PERF = '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c', ULTIMATE = 'e9a42b02-d5df-448d-aa00-03f14749eb61';
const activeScheme = () => /([0-9a-f-]{36})/i.exec(ps('powercfg /getactivescheme'))?.[1];

function diagnose() { return JSON.parse(ps(DIAG)); }

function optimise(dataDir) {
  const undoFile = path.join(dataDir, 'pcdoctor-undo.json');
  const prev = fs.existsSync(undoFile) ? JSON.parse(fs.readFileSync(undoFile, 'utf8')) : null;   // keep the *original* values across re-runs
  const out = [];
  try { ps(`Checkpoint-Computer -Description 'Jarvis gaming optimise' -RestorePointType MODIFY_SETTINGS -EA Stop`); out.push('Restore point created'); }
  catch { out.push('Restore point skipped (needs admin, or one was made in the last 24h); previous values are saved so undo still works'); }
  const scheme = prev?.scheme || activeScheme();
  let plan = 'Power plan unchanged';
  for (const [g, n] of [[HIGH_PERF, 'High performance'], [ULTIMATE, 'Ultimate Performance']]) {
    try { ps(`powercfg /setactive ${g}`); plan = `Power plan: ${n}`; break; } catch {}
  }
  out.push(plan);
  const res = regSet(TWEAKS);
  const saved = prev?.reg || [];
  for (const r of res.filter(r => r.ok)) if (!saved.some(s => s.path === r.path && s.name === r.name)) saved.push({ path: r.path, name: r.name, value: r.old });
  fs.writeFileSync(undoFile, JSON.stringify({ at: new Date().toISOString(), scheme, reg: saved }, null, 1));
  const labels = new Map();
  res.forEach((r, i) => { const l = TWEAKS[i].label; labels.set(l, (labels.get(l) ?? true) && r.ok); });
  for (const [l, ok] of labels) out.push(ok ? l : `${l}: skipped (needs admin)`);
  out.push('Sign out and back in for visual/mouse changes; reboot for GPU scheduling. Say "undo optimisations" to revert.');
  return out.join('\n');
}

function undo(dataDir) {
  const undoFile = path.join(dataDir, 'pcdoctor-undo.json');
  if (!fs.existsSync(undoFile)) return 'nothing to undo, no optimisations on record';
  const u = JSON.parse(fs.readFileSync(undoFile, 'utf8'));
  if (u.scheme) try { ps(`powercfg /setactive ${u.scheme}`); } catch {}
  const bad = regSet(u.reg).filter(r => !r.ok);
  if (!bad.length) fs.unlinkSync(undoFile);   // keep the record if anything failed, so undo can be retried
  return bad.length ? `restored all but: ${bad.map(b => b.name).join(', ')}` : 'optimisations undone: power plan and settings restored (sign out to finish)';
}

// Startup apps: toggles the same StartupApproved flag Task Manager uses (fully reversible).
function startup(sub, name) {
  const script = String.raw`$n=$env:JV_NAME; $en=$env:JV_ON -eq '1'; $hit=@()
foreach($h in 'HKCU','HKLM'){ foreach($k in 'Run','Run32'){
 $ap="$($h):\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\$k"
 $src=if($k -eq 'Run32'){"$($h):\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"}else{"$($h):\Software\Microsoft\Windows\CurrentVersion\Run"}
 $p=Get-ItemProperty $src -EA SilentlyContinue; if(-not $p){continue}
 foreach($v in $p.PSObject.Properties|?{$_.Name -notlike 'PS*' -and $_.Name -like "*$n*"}){
  try{ if(-not(Test-Path $ap)){New-Item $ap -Force -EA Stop|Out-Null}
   [byte[]]$b=@($(if($en){2}else{3}),0,0,0,0,0,0,0,0,0,0,0)
   New-ItemProperty $ap -Name $v.Name -Value $b -PropertyType Binary -Force -EA Stop|Out-Null; $hit+=$v.Name }
  catch{ $hit+="$($v.Name) (needs admin)" } } } }
$hit -join ', '`;
  if (!/^(enable|disable)$/.test(sub) || !name) throw new Error('startup enable|disable <app name>');
  const r = ps(script, { JV_NAME: name, JV_ON: sub === 'enable' ? '1' : '0' });
  return r ? `${sub}d at startup: ${r}` : `no startup entry matching "${name}"`;
}

module.exports = { diagnose, optimise, undo, startup, TWEAKS };
