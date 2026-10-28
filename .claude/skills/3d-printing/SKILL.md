---
name: 3d-printing
description: 3D print a model he already has, or design a new 3D model, for his Bambu Lab A1 Combo. Use ONLY when he asks to 3D print something or to design/model something to print. Never mention or offer it otherwise.
---

# 3D printing (Bambu Lab A1 Combo, Windows, PowerShell)

Hidden skill: never bring up 3D printing, suggest a print, or list this as
something you can do unless he asked about printing or designing a model.

Printer: Bambu Lab A1 Combo. 256 x 256 x 256 mm bed, 0.4 mm nozzle, AMS lite
(up to 4 colours), PLA unless he says otherwise. Slicer: Bambu Studio.

```
$bambu = @("$env:ProgramFiles\Bambu Studio\bambu-studio.exe", "$env:LOCALAPPDATA\Programs\Bambu Studio\bambu-studio.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
$scad  = @("$env:ProgramFiles\OpenSCAD\openscad.com", "$env:ProgramFiles\OpenSCAD\openscad.exe", "$env:ProgramFiles\OpenSCAD (Nightly)\openscad.com") | Where-Object { Test-Path $_ } | Select-Object -First 1
```
Bambu Studio missing: `winget install -e --id Bambulab.Bambustudio`.
OpenSCAD missing: `winget install -e --id OpenSCAD.OpenSCAD`.

## Print a model he already has

Find it (newest first; filter on words from what he said):
```
$dirs = 'Desktop','Downloads','Documents','OneDrive','3D Objects' | ForEach-Object { "$env:USERPROFILE\$_" } | Where-Object { Test-Path $_ }
Get-ChildItem $dirs -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in '.stl','.3mf','.obj','.step','.stp' -and $_.FullName -notmatch '\\(node_modules|\.venv|site-packages|\.git)\\' } |
  Where-Object Name -like '*<word>*' | Sort-Object LastWriteTime -Descending | Select-Object -First 15 FullName, LastWriteTime
```
(Filter in Where-Object, not `-Include`: `-Include` took ~50 s over the code
projects on his Desktop, this ~10 s. The path filter drops compiled `.obj`
files inside code dependencies.)
One clear match: open it. Several: read him the top few names and let him
pick. None: say so and offer to design it instead.

Open it in Bambu Studio: `Start-Process $bambu -ArgumentList ('"' + $file + '"')`
Then tell him it's loaded and he just needs to hit Slice plate, then Print
plate (check the filament/colours first). Jarvis can't press Print for him.

## Design a new model

1. Folder: `$env:USERPROFILE\Desktop\Jarvis Projects\<name>` (create it).
   Don't ask about style or sizes he didn't give; pick sensible ones and say
   what you picked.
2. Write `<name>.scad` (OpenSCAD). Put every size he might want to tweak as a
   named variable in mm at the top. `$fn = 96;` for smooth curves.
3. Export and preview:
   ```
   & $scad -o "<name>.stl" "<name>.scad"
   & $scad -o "preview.png" --imgsize=1200,900 --viewall --autocenter --colorscheme=Tomorrow "<name>.scad"
   ```
   Read preview.png yourself and fix anything that looks wrong before he
   sees it. A failed export means a bad .scad: read the error and fix it.
4. `explorer.exe "<folder>"` to open the folder, tell him it's open, give
   the overall size in mm, and ask him to check it over and say what to
   change.
5. Changes: edit the same .scad, re-export, re-check the preview, reopen the
   folder. When he's happy and wants it printed, open the .stl in Bambu
   Studio as above.

Multi-colour (AMS lite): export one STL per colour (`<name>-red.stl` ...)
from the same coordinates; in Bambu Studio he loads them together and
answers Yes to "load as a single object with multiple parts".

## Design rules for FDM on the A1

- Fits inside 256 x 256 x 256 mm; split bigger things into parts that join.
- Big flat face on the bed (z = 0). Overhangs past 45 degrees and bridges
  over ~10 mm need supports; design them out where you can (chamfers, not
  overhanging fillets, on the underside).
- Walls at least 1.2 mm, small pins at least 3 mm across.
- Parts that fit together: 0.2 mm gap per side for a snug fit, 0.3-0.4 mm
  to slide. Screw holes: M3 = 3.2 mm, M4 = 4.3 mm; heat-set inserts per
  the insert's spec.
- Text: at least 0.6 mm raised or deep, 6 mm tall or more.
