---
name: betbuilder
description: Research and build a football bet builder for a given day. Use when the user asks for a "betbuilder", "bet builder", "acca" or betting tips for a day or fixture (e.g. "give me a betbuilder for Saturday").
---

# Bet builder research

He wants a researched bet builder, not a guess. Do the legwork with
WebSearch/WebFetch, then hand him the picks with the reasoning behind them.
You never place bets, log in to bookmakers or touch his accounts.

## 1. Pin the day

Work out the actual date from his words against today's real date
("Saturday" = the coming Saturday). Default to football; if he names a
sport, league or match, stick to it.

## 2. Find the fixtures

WebSearch the fixture list for that date (e.g. "Premier League fixtures
<date>", "football fixtures <date> UK"). Note kick-off times. Skip games
already started or finished.

## 3. Gather tips (spend real effort here, at least 8-10 searches)

- **Tipster sheets:** search for BadmanBetting first ("BadmanBetting <date>",
  "BadmanBetting sheet", "BadmanBetting bet builder"), then other tipster
  sheets and pages he'd know: "bet builder tips <date>", "<match> bet
  builder tips", "<match> prediction", "BTTS tips <date>", "corners tips",
  "player shots tips". WebFetch the pages and Google Sheets links that turn
  up (a published Google Sheet usually reads fine; add `/export?format=csv`
  to a docs.google.com/spreadsheets link if the HTML is empty).
- **Twitter/X:** WebSearch with `site:x.com` or `site:twitter.com` plus the
  tipster or match ("site:x.com BadmanBetting", "site:x.com <team> bet
  builder"). x.com pages often won't load without a login, so use the
  search snippets; if you can't read the tweets, say so instead of
  inventing them.
- **Stats and news:** team news, injuries and suspensions, predicted
  line-ups, recent form, head-to-head, goals/BTTS/corners/cards rates,
  referee card averages, player shot and shots-on-target numbers (FBref,
  SofaScore, WhoScored, BBC Sport, Sky Sports, official club sites).

Never fetch or scrape with Bash/curl/PowerShell; WebSearch/WebFetch only.

## 4. Build it

- Pick **one match** (a classic bet builder) unless he asks for a
  multi-match builder. Choose the game where tips and stats agree most.
- **3 to 5 legs.** Favour legs that several independent sources back and
  the stats support. Prefer correlated legs that help each other (e.g.
  favourite to win + favourite's striker 1+ shot on target + over 1.5
  goals). Avoid legs that fight each other (BTTS No with over 3.5 goals).
- Drop anything that hinges on a player who's doubtful or not expected to
  start.
- Quote odds only if you actually saw them on a page today, and say where.
  Otherwise say odds are for him to check.
- Optionally give one safer alternative (fewer legs) and one bigger-priced
  swap.

## 5. Present it

Out loud, keep it tight and in Jarvis's voice:

1. The match, kick-off time and date.
2. Each leg with one line of why (the stat or news behind it) and which
   tipsters back it.
3. Confidence: low / medium / high, and the biggest risk to the builder.
4. Sources: the tipster sheets, tweets and stats pages you actually used,
   as links when typing.
5. End with one line: "Bet what you can afford to lose, boss. BeGambleAware.org
   if it stops being fun."

Be honest: if research turned up thin or conflicting tips, say so and
give the builder a lower confidence rather than dressing it up.
