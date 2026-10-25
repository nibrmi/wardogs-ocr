"""Экран итогов матча WARDOGS: победа/поражение, очки команд и деньги за матч.

Использование для проверки:
    python endscreen.py <кадр.jpg> [...]
"""
import re
import sys

import numpy as np
from PIL import Image

from winocr import make_engine, recognize

TITLE = (1000, 150, 2450, 460)    # «ПОБЕДА» / «ПОРАЖЕНИЕ» при 3440x1440
PANEL = (1150, 500, 2300, 1110)   # очки команд и строки с деньгами
ROWS = {  # подпись в игре -> поле (английские — предположение по аналогии, не сверены с английской версией игры)
    "МЕСТО": "place_bonus", "ПОТРАЧЕНО": "spent", "ЗАРАБОТАНО": "earned", "ВОЗВРАЩЕНЫ": "refunded", "ПРИБЫЛЬ": "profit",
    "PLACE": "place_bonus", "SPENT": "spent", "EARNED": "earned", "REFUND": "refunded", "RETURNED": "refunded",
    "PROFIT": "profit",
}
MONEY_RE = re.compile(r"([-–—]?)\s*\$\s*([\dЗО ]+)")


def bright(img: Image.Image, scale=2):
    """Для цветного текста (красные и зелёные суммы): берём самый яркий канал из R, G, B вместо обычного серого,
    иначе красное и зелёное на тёмном фоне становится тёмно-серым и OCR его теряет."""
    a = np.asarray(img.convert("RGB")).max(axis=2).astype(np.uint8)
    out = Image.fromarray(a)
    return out.resize((out.width * scale, out.height * scale), Image.LANCZOS) if scale != 1 else out


def rows_of(lines, tolerance=14):
    rows = []
    for l in sorted(lines, key=lambda l: (l["box"][1] + l["box"][3]) / 2):
        cy = (l["box"][1] + l["box"][3]) / 2
        if rows and abs(rows[-1][0] - cy) <= tolerance:
            rows[-1][1].append(l)
        else:
            rows.append([cy, [l]])
    return [" ".join(p["text"] for p in sorted(parts, key=lambda p: p["box"][0])) for _, parts in rows]


def money(text):
    # «-$10 310» в красном OCR иногда читает как «-610 310»: знак доллара принят за 6
    text = re.sub(r"([-–—])\s*6(?=\d{1,3}\s\d{3}\b)", r"\1$", text)
    m = MONEY_RE.search(text)
    if not m:
        return None
    value = int(m.group(2).replace(" ", "").replace("З", "3").replace("О", "0"))
    return -value if m.group(1) else value


def read(engine, frame: Image.Image):
    """frame — кадр 3440x1440. Возвращает dict с итогами или None, если это не экран итогов."""
    from layout import centered  # экран итогов стоит по центру — на экранах другой ширины сдвигаем
    title = " ".join(l["text"] for l in recognize(engine, bright(frame.crop(centered(TITLE, frame.width)), scale=1)))
    up = title.upper()
    result = ("победа" if "ПОБЕД" in up or "VICTORY" in up else
              "поражение" if "ПОРАЖ" in up or "DEFEAT" in up else None)
    if result is None:
        return None
    out = {"result": result}
    for text in rows_of(recognize(engine, bright(frame.crop(centered(PANEL, frame.width))))):
        for word, field in ROWS.items():
            if word in text.upper():
                value = money(text)
                if value is not None:
                    out[field] = abs(value) if field != "spent" else -abs(value)
    return out


class EndScreen:
    """Строки на экране итогов выезжают по очереди, поэтому читаем его несколько кадров подряд
    и копим поля. Когда экран пропал — итоги матча готовы."""

    def __init__(self, engine):
        self.engine = engine
        self.current = None

    def feed(self, frame):
        """Вызывать на каждом кадре, где открыта вкладка «СЧЕТ». Возвращает итоги, когда экран закрылся."""
        r = read(self.engine, frame) if frame is not None else None
        if r:
            self.current = {**(self.current or {}), **r}
            return None
        done, self.current = self.current, None
        return done


if __name__ == "__main__":
    e = make_engine("ru")
    es = EndScreen(e)
    for path in sys.argv[1:] + [None]:
        done = es.feed(Image.open(path) if path else None)
        if done:
            print("итоги матча:", done)
