"""Пересчитать ленту убийств сессии по её сохранённым снимкам (после улучшения распознавания).

Использование:
    python reprocess.py sessions/2026-10-25_15-18 --nick Nikita
Старый CSV сохраняется рядом как <имя>.old.csv.
"""
import argparse
import csv
import glob
import os
import re
import shutil

from PIL import Image

from feedreader import FeedReader
from live import FIELDS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stem", help="путь к сессии без расширения, например sessions/2026-10-25_15-18")
    ap.add_argument("--nick", required=True)
    args = ap.parse_args()

    shots = sorted(glob.glob(args.stem + "_shots/*.jpg"))
    if not shots:
        raise SystemExit(f"нет снимков в {args.stem}_shots")
    reader, kills = FeedReader(args.nick), []
    for p in shots:
        # имя снимка: ЧЧММСС_секунды.jpg
        clock, t = re.search(r"(\d{6})_(\d+)\.jpg$", p).groups()
        for k in reader.read(Image.open(p), int(t)):
            k["clock"] = f"{clock[:2]}:{clock[2:4]}:{clock[4:]}"
            kills.append(k)
    kills += reader.flush()
    for k in kills:
        k["time"] = f"{int(k['t'] // 60)}:{int(k['t'] % 60):02d}"

    if os.path.exists(args.stem + ".csv"):
        shutil.copy(args.stem + ".csv", args.stem + ".old.csv")
    with open(args.stem + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(kills)
    mine = [k for k in kills if k["mine"]]
    print(f"{len(kills)} убийств в ленте, с тобой {len(mine)}: " +
          "; ".join(f"{k['mine']} {k['victim'] if k['mine'] == 'убил' else k['killer']}" for k in mine))


if __name__ == "__main__":
    main()
