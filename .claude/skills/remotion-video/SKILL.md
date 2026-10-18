---
name: remotion-video
description: Make motion graphics and animated videos in code with Remotion (React). Use when he asks for an intro, outro, promo, explainer, animated logo, lyric/kinetic text video, stream overlay animation, data animation or any "motion design" video.
---

# Motion design with Remotion

Remotion's own agent skills (remotion-dev/skills, the most-installed video
skill pack) hold the real know-how. Fetch them, then follow them.

1. Get or refresh the official skills (PowerShell):
   ```
   $s = "$env:APPDATA\jarvis\remotion-skills"
   if (Test-Path $s) { git -C $s pull -q } else { git clone -q --depth 1 https://github.com/remotion-dev/skills $s }
   ```
2. Read `$s\skills\remotion-best-practices\SKILL.md` and the reference files it
   points to for the task (create, markup, captions, render). They win over
   anything below on Remotion APIs.
3. The project goes in `%USERPROFILE%\Desktop\Jarvis Projects\<project name>`
   (create the folder). Scaffold there with
   `npx create-video@latest --yes --blank --no-tailwind <project name>` then `npm i`.
4. Start `npx remotion studio` so he can watch it build in the browser, and
   keep it running while you work.
5. Render only when he wants the file ("render it", "export", "give me the
   MP4"): `npx remotion render`, output into the project's `out` folder, then
   open that folder in Explorer and say so.

Defaults when he doesn't say: 1920x1080 at 30fps, about 10 seconds; for a
TikTok/Shorts/Reels clip 1080x1920. Pick the style yourself (bold, on-brand
for his channel if you know it) and say what you chose. A voiceover through
a paid TTS service (Remotion's guide uses ElevenLabs) needs his go-ahead and
his own key; never read or reveal stored keys.
