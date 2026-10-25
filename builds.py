"""Сборка оружия: какие модули стоят и что они дают вместе.

В инвентаре и при обыске справа от картинки оружия — четыре ячейки модулей квадратом 2×2:
    магазин   | прицел
    подствол  | дуло
В углу каждой ячейки крупно написан вес модуля. По весу, типу ячейки и совместимости с этим оружием
модуль находится в таблице (data/attachments.json), а дальше складываем эффекты.

Как эффекты складываются, официально не сказано. WardogTools.gg по файлам игры пишет, что множители
перемножаются (−30% и −20% → ×0,7 × ×0,8 = −44%), так и считаем.

Проверка на кадре:
    python builds.py <кадр.jpg 3440x1440>
"""
import re
import sys
from difflib import SequenceMatcher

from PIL import Image, ImageOps

from journal import WEAPONS
from shoptip import kg, load_items, loose
from winocr import make_engine, recognize

WEIGHT_RE = re.compile(r"(\d+)[,.](\d\d)\b")
SLOT_ORDER = ["magazine", "optic", "underbarrel", "muzzle"]  # слева направо, сверху вниз
SLOT_NAMES = {"magazine": "Магазин", "optic": "Прицел", "underbarrel": "Подствол", "muzzle": "Дуло"}


def slot_of(item):
    """Тип ячейки для предмета из таблицы — по адресу на сайте и по названию."""
    iid, name = item["id"].lower(), item["name_ru"].lower()
    if iid.startswith(("muzl", "mzl")) or any(w in name for w in ("тормоз", "глушит", "пламегас", "компенсат", "чок", "дульн")):
        return "muzzle"
    if "mag" in iid or "магазин" in name:
        return "magazine"
    if iid.startswith(("sght", "opt")) or "scope" in iid or any(w in name for w in ("прицел", "оптик", "коллимат")):
        return "optic"
    if iid.startswith(("fgrp", "fgp")) or "foregrip" in iid or any(w in name for w in ("рукоят", "сошк", "подствол")):
        return "underbarrel"
    return None


def weapon_of(text):
    """Название оружия из подписи под картинкой — только из известного списка (OCR не даём выдумывать)."""
    key = loose(text)
    if len(key) < 3:
        return None
    best = max(WEAPONS, key=lambda w: SequenceMatcher(None, key, loose(w)).ratio())
    return best if SequenceMatcher(None, key, loose(best)).ratio() >= 0.8 else None


def fits(item, weapon):
    return any(SequenceMatcher(None, loose(f), loose(weapon)).ratio() >= 0.8 for f in item.get("fits", []))


def identify(items, slot, weight, weapon):
    """Модули с таким весом и типом ячейки, подходящие к оружию. Возвращает список кандидатов."""
    cands = [it for it in items if slot_of(it) == slot and kg(it["stats"].get("Вес")) is not None
             and abs(kg(it["stats"]["Вес"]) - weight) < 0.006]
    fitting = [it for it in cands if fits(it, weapon)]
    return fitting or cands


def combine(modules):
    """Итог по характеристикам: множители перемножаются. modules — список предметов из таблицы."""
    total = {}
    for it in modules:
        for stat, value in it["stats"].items():
            m = re.match(r"([+\-]?\d+)%", value)
            if m:
                total[stat] = total.get(stat, 1.0) * (1 + int(m.group(1)) / 100)
    return {stat: round((mult - 1) * 100) for stat, mult in total.items()}


class Builds:
    def __init__(self, engine=None):
        self.engine = engine or make_engine("ru")
        self.items = load_items()

    def find(self, frame: Image.Image, lines):
        """frame — кадр 3440x1440, lines — уже распознанные строки всего кадра.
        Возвращает [{"weapon", "pos": (x, y) правый верхний угол ячеек, "slots": {...}, "total": {...}}]."""
        out = []
        for name_line in lines:
            weapon = weapon_of(name_line["text"])
            if not weapon:
                continue
            nx, ny = name_line["box"][0], name_line["box"][1]
            # правый край картинки оружия: в той же строке, что название, справа стоит серийный номер («1T3JWY6»)
            same_row = [l for l in lines if abs(l["box"][1] - ny) < 15 and nx + 250 < l["box"][0] < nx + 900]
            if not same_row:
                continue
            edge = max(l["box"][2] for l in same_row)
            x0, y0 = edge + 15, ny - 200   # ячейки модулей — справа от картинки, по всей её высоте
            x1, y1 = x0 + 330, ny + 40
            crop = ImageOps.grayscale(frame.crop((x0, y0, x1, y1)))
            small = recognize(self.engine, crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS))
            weights = []
            for l in small:
                m = WEIGHT_RE.search(l["text"])
                if m and not "/" in l["text"]:
                    cx, cy = (l["box"][0] + l["box"][2]) / 6, (l["box"][1] + l["box"][3]) / 6
                    weights.append((cx, cy, float(f"{m.group(1)}.{m.group(2)}")))
            if not weights:
                continue
            # ячейки 2×2: делим по середине области
            midx, midy = (x1 - x0) / 2, (y1 - y0) / 2
            slots = {}
            for cx, cy, w in weights:
                slot = SLOT_ORDER[(2 if cy > midy else 0) + (1 if cx > midx else 0)]
                cands = identify(self.items, slot, w, weapon)
                slots[slot] = {"weight": w, "candidates": cands}
            known = [s["candidates"][0] for s in slots.values() if len(s["candidates"]) == 1]
            out.append({"weapon": weapon, "pos": (x1, y0), "slots": slots, "total": combine(known),
                        "unsure": [SLOT_NAMES[k] for k, s in slots.items() if len(s["candidates"]) != 1]})
        return out


if __name__ == "__main__":
    b = Builds()
    frame = Image.open(sys.argv[1]).convert("RGB")
    lines = recognize(b.engine, ImageOps.grayscale(frame))
    for build in b.find(frame, lines):
        print("===", build["weapon"])
        for slot, s in build["slots"].items():
            names = " / ".join(c["name_ru"] for c in s["candidates"]) or "нет в таблице"
            print(f"  {SLOT_NAMES[slot]:<9} {s['weight']:.2f} кг -> {names}")
        print("  Итого:", build["total"], "| не уверен:", build["unsure"])
