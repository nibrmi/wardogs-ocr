"""Группирует похожие иконки оружия, чтобы подписать каждую группу один раз.

Использование:
    python cluster_icons.py out/icons --out clusters

Результат:
    clusters/overview.png      — все группы на одной картинке: номер, сколько раз встречалась, 12 примеров
    clusters/group_XX.png      — эталон каждой группы (самая «типичная» иконка)
Чтобы подписать оружие, скопируй group_XX.png в папку templates/ и назови файл именем оружия,
например templates/АК-74.png. Несколько эталонов одного оружия: АК-74.png, АК-74_2.png.
"""
import argparse
import glob
import os

import numpy as np
from PIL import Image, ImageDraw

from icons import SIZE, distance, weapon_icon

THRESHOLD = 0.45  # иконки ближе этого попадают в одну группу


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("icons")
    ap.add_argument("--out", default="clusters")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    items = []
    for path in sorted(glob.glob(os.path.join(args.icons, "*.png"))):
        icon = weapon_icon(Image.open(path))
        if icon is not None:
            items.append((path, icon))
    print(f"иконок с оружием: {len(items)}")

    # Жадная группировка: каждую иконку кладём в группу с ближайшим эталоном или заводим новую группу.
    groups = []  # {"members": [...], "ref": icon}
    for path, icon in items:
        best = min(groups, key=lambda g: distance(g["ref"], icon), default=None)
        if best is not None and distance(best["ref"], icon) < THRESHOLD:
            best["members"].append((path, icon))
        else:
            groups.append({"members": [(path, icon)], "ref": icon})

    # Эталон группы — участник, который в сумме ближе всех к остальным (медоид).
    for g in groups:
        m = g["members"][:60]
        g["ref"] = min(m, key=lambda a: sum(distance(a[1], b[1]) for b in m))[1]
    groups.sort(key=lambda g: -len(g["members"]))

    row_h, cell_w, n_examples = SIZE[1] + 8, SIZE[0] + 8, 12
    sheet = Image.new("L", (90 + cell_w * n_examples, row_h * len(groups)), 30)
    draw = ImageDraw.Draw(sheet)
    for gi, g in enumerate(groups):
        ref_img = Image.fromarray((g["ref"][0] * 255).astype(np.uint8))
        ref_img.save(os.path.join(args.out, f"group_{gi:02d}.png"))
        draw.text((4, gi * row_h + 10), f"{gi:02d}  x{len(g['members'])}", fill=255)
        for k, (_, icon) in enumerate(g["members"][:n_examples]):
            sheet.paste(Image.fromarray((icon[0] * 255).astype(np.uint8)), (90 + k * cell_w, gi * row_h + 4))
    sheet.save(os.path.join(args.out, "overview.png"))
    print(f"групп: {len(groups)}; размеры: {[len(g['members']) for g in groups]}")


if __name__ == "__main__":
    main()
