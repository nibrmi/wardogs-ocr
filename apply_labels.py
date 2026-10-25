"""Копирует эталоны групп из clusters/ в templates/ под названиями из labels.txt.

templates/ — это «словарь» распознавания: каждая картинка там — образец оружия,
имя файла — его название (АК.png, АК_2.png, ... — несколько образцов одного оружия).
"""
import os
import shutil
from collections import Counter

os.makedirs("templates", exist_ok=True)
for f in os.listdir("templates"):
    os.remove(os.path.join("templates", f))

used = Counter()
with open("labels.txt", encoding="utf-8") as f:
    for line in f:
        line = line.split("#")[0].strip()
        if "=" not in line:
            continue
        group, name = (s.strip() for s in line.split("=", 1))
        used[name] += 1
        suffix = "" if used[name] == 1 else f"_{used[name]}"
        shutil.copy(os.path.join("clusters", f"group_{int(group):02d}.png"), os.path.join("templates", f"{name}{suffix}.png"))

print(f"эталонов: {sum(used.values())}, оружия: {len(used)}")
