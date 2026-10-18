---
name: minecraft-server
description: Set up and run a Minecraft Java server (Paper), install plugins, build things in the world with datapacks, and write custom Paper/Spigot plugins. Use when he asks for a Minecraft server, plugins, a minigame, server commands or anything Minecraft-server related.
---

# Minecraft servers and plugins (Windows, PowerShell)

Everything goes in `%USERPROFILE%\Desktop\Jarvis Projects\<name>` (create it).
Open the folder in Explorer when done and say so. Default to the newest stable
Paper unless he names a version or his friends play an older one.

## Java

`java -version`. Minecraft 26.x needs Java 25; 1.20.5 to 1.21.x need Java 21.
If it's missing or too old: `winget install -e --id EclipseAdoptium.Temurin.25.JDK`
(or `.21.JDK`), then use the full path to the new `java.exe` in that session.

## A Paper server

PaperMC's download API wants a real User-Agent:
```
$h = @{ 'User-Agent' = 'Jarvis/3 (https://github.com/MarkyADHD/jarvis)' }
$p = Invoke-RestMethod https://fill.papermc.io/v3/projects/paper -Headers $h
$v = '<version>'   # newest release from $p.versions (skip -pre / -rc)
$b = Invoke-RestMethod "https://fill.papermc.io/v3/projects/paper/versions/$v/builds" -Headers $h
$url = ($b | Where-Object channel -eq 'STABLE' | Select-Object -First 1).downloads.'server:default'.url
Invoke-WebRequest $url -OutFile paper.jar -Headers $h
```
Then in the server folder:
- `eula.txt` containing `eula=true`; tell him that accepts Mojang's EULA.
- `start.bat`: `java -Xms2G -Xmx4G -jar paper.jar --nogui` then `pause`
  (raise -Xmx for many players or big modpacks).
- `server.properties` only with what he asked for (motd, gamemode,
  difficulty, max-players, white-list, online-mode stays true); Paper fills
  in the rest on first start.
Start it with `start "" start.bat` from that folder (its own window, so it
keeps running). Friends on his network join on his LAN IP:25565. Over the
internet needs port 25565 forwarded on his router or a tunnel like
playit.gg; explain, don't touch his router.

## Plugins

Prefer Modrinth (no login, has an API):
```
$f = (Invoke-RestMethod "https://api.modrinth.com/v2/project/<slug>/version?loaders=[%22paper%22]&game_versions=[%22$v%22]" -Headers $h)[0].files | Where-Object primary
Invoke-WebRequest $f.url -OutFile "plugins\$($f.filename)"
```
Well-known picks: `luckperms` (permissions), `essentialsx` (basics:
homes, warps, kits), `worldedit` (building), `geyser` + `floodgate`
(Bedrock/console friends can join), `chunky` (pre-generate the world),
`coreprotect` (rollback griefing). Unknown slug: search
`https://api.modrinth.com/v2/search?query=<name>`. Otherwise look it up on Hangar
(hangar.papermc.io) or SpigotMC. Restart the server to load plugins.

## Building things in the world

For structures, arenas or minigame maps, write a datapack:
`world\datapacks\<name>\pack.mcmeta` + `data\<name>\function\*.mcfunction`
full of `fill`/`setblock`/`summon` commands, then in game `/reload` and
`/function <name>:<file>`. Check the pack_format for his version with a
quick search. WorldEdit schematics (`.schem` in `plugins\WorldEdit\schematics`)
for anything he downloads.

## Writing a plugin

Gradle (Kotlin DSL) project, Java toolchain matching the server:
- repository `https://repo.papermc.io/repository/maven-public/`,
  `compileOnly("io.papermc.paper:paper-api:<api version>")`; check the
  current coordinates on docs.papermc.io for that Minecraft version.
- `src/main/resources/plugin.yml` (name, version, main, api-version),
  a main class extending `JavaPlugin`, listeners with `@EventHandler`,
  commands registered in plugin.yml.
- No Gradle on the PC: `winget install -e --id Gradle.Gradle`, then
  `gradle wrapper` once; build with `.\gradlew build`, copy
  `build\libs\*.jar` into the server's `plugins` folder and restart.
Keep it to what he asked for; no NMS, databases or multi-module setups
unless the job needs them.
