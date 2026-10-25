# WARDOGS OCR

[Русский](README.ru.md) · **English**

An unofficial companion tool for [WARDOGS](https://store.steampowered.com/app/1867240/WARDOGS/): it reads what the game
shows on screen and turns it into numbers and statistics.

> Not affiliated with BULKHEAD or Team17. The program **does not touch the game process**, does not read its memory,
> does not intercept network traffic and **never presses anything for the player** — it only receives the image of the
> game window through Windows Graphics Capture (the same mechanism as OBS "Window Capture") and recognises text with
> the built-in Windows OCR.

## Features

| Feature | How it works |
|---|---|
| **Real attachment numbers** | Hover an attachment in the shop or inventory — a small window shows the actual percentages (recoil, spread, ADS time, equip speed) instead of the game's "moderate reduction…". |
| **Weapon build totals** | In the inventory and when looting, sums up what all attachments on a weapon give together. Slot weights are shown with **F**. Effects are multiplied (per the [WardogTools analysis](https://wardogtools.gg/methodology/recoil/)). |
| **Kill tracker** | Reads the kill feed: who killed whom, with which weapon (by icon), from what distance. |
| **Damage log** | Press **B** on the death screen — the program reads the log: damage by body part, hits, kills and every money reward. |
| **Match results** | Victory/defeat, money earned, spent, profit. |
| **Statistics page** | The "Statistics" button: K/D, weapons, where you hit, who kills you most, how you earn money, top players, weapon meta, session history. Everything stays local, opens in your browser. |

## Getting started

**Ready-to-use program:** download `WARDOGS-OCR.zip` from [Releases](../../releases), unzip it, run `WARDOGS-OCR.exe`,
enter your nickname, tick what you need and press "Start". Data is saved to `Documents\WARDOGS-OCR`.

Requirements:
- Windows 10/11, the game in **"Windowed Fullscreen"** (borderless) mode;
- **Russian Windows OCR**: Settings → Time & language → Language & region → add Russian. It is needed even for the
  English game (it reads both Cyrillic and Latin). The program warns you at startup if it is missing.

**From source** (Python 3.12):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py                  # settings window
```

Build the exe: `powershell -ExecutionPolicy Bypass -File build.ps1` (result: `dist\WARDOGS-OCR.zip`).

## Languages

- **Program UI** — Russian or English (selector in the main window; defaults to your Windows language).
- **Game language** doesn't need to be chosen: both the Russian and the English game text are recognised.
  Attachment names and numbers are available in both languages.
- ⚠️ The English game version is only partially verified: attachment tooltips rely on English data from wardogs.zone,
  while the English names of menu tabs, the damage log and the match result screen are educated guesses awaiting a
  check on a recording. Screenshots of the English UI are very welcome (open an issue).

## Performance

The main knob is "Check the screen every N s" in the program window. Text recognition is the main CPU work: checking
less often lowers the load, but hints appear later and short kill feed lines may be missed. The program runs at a lower
process priority so it doesn't take time away from the game.

## Limitations (honestly)

- **Screen resolution.** The game UI scales with screen height; the program accounts for that (`layout.py`).
  Tested on recordings:

  | Resolution | Kill feed | Attachment tooltips | Build totals |
  |---|---|---|---|
  | 3440×1440 (21:9) | ✅ | ✅ | ✅ |
  | 1920×1080 (16:9) | ✅ | ✅ | ⚠️ slot weights read partially |
  | 1600×900 (16:9) | ⚠️ nickname errors, weapon often "?" | ✅ | ❌ weights too small |

  Higher resolution means better accuracy: at 1080p and below small text is at the limit of what OCR can read.
  The damage log and match result screen haven't been verified at 16:9 yet.
- **Nicknames** are recognised with errors; similar variants are merged, but not always perfectly.
- **Weapon names** in the kill feed come from icons (`templates/` folder); some names were matched by silhouette.
- **The damage log** is only partly visible — the more often you open it (B on every death), the fuller your stats.
- **Attachment numbers** come from the fan site [wardogs.zone](https://wardogs.zone), not official; they may lag behind after patches.

## Data

Attachment numbers are from **[wardogs.zone](https://wardogs.zone)**, used **with the site owner's permission** — thank
you! The table is in `data/attachments.json`; to refresh it after a game patch, delete `data/cache/` and run
`scrape_attachments.py` (it fetches `/database/` pages one per second, within robots.txt).

## Project structure (for developers)

| File | What it does |
|---|---|
| `app.py` | settings window, exe entry point |
| `wardogs.py` | main loop: capture, screen detection, all recognition; console mode |
| `live.py` | window capture (Windows Graphics Capture), session and files |
| `feedreader.py` | kill feed: OCR, row parsing, duplicate merging |
| `icons.py`, `templates/` | weapon recognition by icon |
| `shoptip.py`, `overlay.py` | item tooltip and on-top windows |
| `builds.py` | weapon build totals |
| `journal.py`, `damagelog.py` | damage log |
| `endscreen.py` | match result screen |
| `stats.py` | statistics page |
| `i18n.py` | program UI texts in Russian and English |
| `layout.py` | how the game UI behaves at different resolutions |
| `winocr.py` | Windows OCR wrapper |
| `scrape_attachments.py` | builds the attachment table |
| `killfeed.py`, `cluster_icons.py`, `apply_labels.py`, `match_refs.py`, `reprocess.py` | tools: video analysis, icon templates, re-processing sessions |

Code comments are in Russian.

## License

MIT — see [LICENSE](LICENSE).
