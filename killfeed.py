"""Читает ленту убийств WARDOGS с кадров записанного видео и находит события с твоим ником.

Использование:
    python killfeed.py <папка с кадрами f_0001.jpg...> --nick Nikita [--step 5] [--out out]

Кадры должны быть 3440x1440 и идти через равные промежутки (--step секунд).
Результат: out/all_kills.csv (все убийства), out/my_kills.csv (только с тобой)
и out/icons/ (вырезанные иконки оружия, по ним строятся эталоны в templates/).
"""
import argparse
import csv
import glob
import os
from collections import Counter

from PIL import Image

from feedreader import KILLFEED, FeedReader, format_kill

FIELDS = ["time", "frame", "killer", "victim", "weapon", "distance_m", "mine"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--nick", required=True)
    ap.add_argument("--step", type=float, default=5.0, help="секунд между кадрами")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    os.makedirs(os.path.join(args.out, "icons"), exist_ok=True)
    reader = FeedReader(args.nick)
    frames = sorted(glob.glob(os.path.join(args.frames, "f_*.jpg")))

    kills = []

    def collect(new):
        for kill in new:
            t = kill["t"]
            kill.update(time=f"{int(t // 60)}:{int(t % 60):02d}", frame=os.path.basename(frames[round(t / args.step)]))
            kills.append(kill)
            kill["icon"].save(os.path.join(args.out, "icons", f"{len(kills):04d}_{os.path.splitext(kill['frame'])[0]}.png"))

    for i, path in enumerate(frames):
        collect(reader.read(Image.open(path).crop(KILLFEED), i * args.step))
        if i % 100 == 0:
            print(f"кадр {i}/{len(frames)}, убийств найдено: {len(kills)}")
    collect(reader.flush())

    for name, rows in (("all_kills.csv", kills), ("my_kills.csv", [k for k in kills if k["mine"]])):
        with open(os.path.join(args.out, name), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    mine = [k for k in kills if k["mine"]]
    print(f"\nВсего убийств в ленте: {len(kills)}")
    print(f"С тобой: убил {sum(k['mine'] == 'убил' for k in mine)}, умер {sum(k['mine'] == 'умер' for k in mine)}")
    for k in mine:
        print("  " + format_kill(k) + f"   [{k['frame']}]")

    print("\nОружие по всем убийствам в ленте:")
    for weapon, n in Counter(k["weapon"] or "нет иконки" for k in kills).most_common():
        print(f"  {n:4d}  {weapon}")


if __name__ == "__main__":
    main()
