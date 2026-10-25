"""Сопоставляет наши группы иконок с рендерами оружия из базы (wardogtools.gg).

У рендеров прозрачный фон, поэтому их альфа-канал — готовый силуэт оружия, как иконка в ленте убийств.
Приводим силуэт к тому же виду, что и иконки (icons.normalize), и ищем ближайший.

Использование:
    python match_refs.py <папка с рендерами *.webp> [--clusters clusters]
Печатает для каждой группы три самых похожих оружия и сохраняет clusters/match.png для проверки глазами.
"""
import argparse
import glob
import os
import re

import numpy as np
from PIL import Image

from icons import SIZE, distance, normalize


def silhouette(path):
    alpha = Image.open(path).convert("RGBA").getchannel("A")
    # normalize() ищет «яркие» пиксели — подаём альфу как яркость: непрозрачное = белое
    cols = np.where((np.asarray(alpha) > 40).any(axis=0))[0]
    return normalize(alpha.point(lambda v: 255 if v > 40 else 0), cols[0], cols[-1] + 1)


def group_mask(path):
    mask = (np.asarray(Image.open(path).convert("L")) > 127).astype(np.float32)
    rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
    return mask, (cols[-1] - cols[0] + 1) / (rows[-1] - rows[0] + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("refs")
    ap.add_argument("--clusters", default="clusters")
    args = ap.parse_args()

    refs = [(os.path.splitext(os.path.basename(p))[0], silhouette(p)) for p in sorted(glob.glob(os.path.join(args.refs, "*.webp")))]
    groups = sorted(glob.glob(os.path.join(args.clusters, "group_*.png")))

    w, h = SIZE
    sheet = Image.new("L", ((w + 8) * 4, (h + 8) * len(groups)), 30)
    for gi, path in enumerate(groups):
        g = group_mask(path)
        ranked = sorted(((distance(g, r), name, r) for name, r in refs), key=lambda x: x[0])[:3]
        num = re.search(r"(\d+)", os.path.basename(path)).group(1)
        print(num, " | ".join(f"{name} {d:.2f}" for d, name, _ in ranked))
        sheet.paste(Image.fromarray((g[0] * 255).astype(np.uint8)), (4, gi * (h + 8) + 4))
        for k, (_, _, r) in enumerate(ranked):
            sheet.paste(Image.fromarray((r[0] * 160).astype(np.uint8)), ((k + 1) * (w + 8) + 4, gi * (h + 8) + 4))
    sheet.save(os.path.join(args.clusters, "match.png"))


if __name__ == "__main__":
    main()
