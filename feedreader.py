"""Распознавание ленты убийств WARDOGS — общая часть для разбора видео (killfeed.py) и живого трекера (live.py).

На вход: картинка области ленты в масштабе 3440x1440 и время в секундах.
На выход: новые убийства (повторы из предыдущих снимков отброшены).
"""
import difflib
import os
import re
from collections import Counter

from PIL import Image, ImageOps

from icons import classify, load_templates
from paths import resource
from winocr import make_engine, recognize

KILLFEED = (30, 600, 830, 900)  # область ленты при 3440x1440: x0, y0, x1, y1
SCALE = 3                       # OCR лучше читает мелкий шрифт, если картинку увеличить
ROW_TOLERANCE = 25              # строки OCR, чьи центры ближе (в увеличенных пикселях), — одна строка ленты
KILLER_MAX_X = 330              # ник убийцы всегда начинается у левого края ленты
DEDUP_SECONDS = 30              # одно убийство висит в ленте несколько секунд — не считаем его повторно
FINAL_AFTER = 3                 # строку не видно столько секунд — значит, ушла из ленты, выдаём убийство
ICON_HALF_HEIGHT = 45           # половина высоты полосы с иконкой (строки ленты идут через ~96 увеличенных пикселей)
MIN_ICON_GAP = 60               # минимум места под иконку оружия между никами (в увеличенных пикселях)
WORD_GAP = 60                   # промежуток между словами шире этого — там была иконка, а не пробел в нике

# OCR иногда путает похожие латинские и русские буквы. Сводим всё к латинице перед сравнением.
HOMOGLYPHS = str.maketrans("аеорсухкмтвнАЕОРСУХКМТВН0", "aeopcyxkmtbhAEOPCYXKMTBHO")
DISTANCE_RE = re.compile(r"\[\s*(\d+)\s*[mMтТмМ]\s*\]?")


def clean_name(text):
    """Убирает мусор по краям: значки фракций и черепа OCR читает как 1–2 случайных символа."""
    text = DISTANCE_RE.sub(" ", text)
    tokens = text.split()
    while tokens and len(tokens[0]) <= 2:
        tokens.pop(0)
    while tokens and len(tokens[-1]) <= 2:
        tokens.pop()
    return " ".join(tokens)


def norm(name):
    return name.translate(HOMOGLYPHS).lower().replace(" ", "")


def same_player(a, b, threshold=0.8):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() >= threshold


def group_rows(lines):
    """Склеивает куски текста OCR в строки ленты по вертикали."""
    rows = []
    for line in sorted(lines, key=lambda l: (l["box"][1] + l["box"][3]) / 2):
        cy = (line["box"][1] + line["box"][3]) / 2
        if rows and abs(rows[-1]["cy"] - cy) <= ROW_TOLERANCE:
            rows[-1]["parts"].append(line)
        else:
            rows.append({"cy": cy, "parts": [line]})
    return rows


def split_on_gaps(line):
    """OCR иногда склеивает всю строку ленты в один кусок: «Nikita 9 [9т] [.mp4]Esso» (иконку оружия он принял за «9»).
    Между ником и иконкой всегда широкий промежуток — режем кусок по таким промежуткам между словами."""
    words = sorted(line["words"], key=lambda w: w[1])
    pieces, current = [], [words[0]]
    for w in words[1:]:
        if w[1] - current[-1][2] >= WORD_GAP:
            pieces.append(current)
            current = []
        current.append(w)
    pieces.append(current)
    y0, y1 = line["box"][1], line["box"][3]
    return [{"text": " ".join(w[0] for w in p), "box": (p[0][1], y0, p[-1][2], y1)} for p in pieces]


def parse_row(row):
    """Строка ленты: [фракция] Убийца [оружие] [череп] [дистанция] Жертва [фракция]."""
    parts = sorted((p for line in row["parts"] for p in split_on_gaps(line)), key=lambda l: l["box"][0])
    full_text = " ".join(p["text"] for p in parts)
    distance = DISTANCE_RE.search(full_text)

    killer_part = parts[0] if parts[0]["box"][0] <= KILLER_MAX_X else None
    victim_part = parts[-1] if parts[-1] is not killer_part else None
    if victim_part is None:
        return None

    # В настоящей строке ленты всегда есть и убийца, и иконка оружия между никами.
    # Надписи в меню продавца и прочий текст на фоне этому не соответствуют.
    if killer_part is None or victim_part["box"][0] - killer_part["box"][2] < MIN_ICON_GAP:
        return None
    killer = clean_name(killer_part["text"])
    victim = clean_name(victim_part["text"])
    if not killer or not victim:
        return None
    return {
        "killer": killer,
        "victim": victim,
        "distance_m": int(distance.group(1)) if distance else "",
        # иконка оружия лежит между ником убийцы и ником жертвы
        "icon_x": (killer_part["box"][2], victim_part["box"][0]),
        # иконки выше текста, поэтому берём фиксированную полосу вокруг центра строки, а не рамку текста
        "y": (row["cy"] - ICON_HALF_HEIGHT, row["cy"] + ICON_HALF_HEIGHT),
    }


TAG_RE = re.compile(r"[\[(][^\])]{0,8}[\])]")


def core_name(name):
    """Ник без тега клана и мусора: «[от] FLEX» -> «flex», «[SMG]Mackan025» -> «mackan025»."""
    from shoptip import loose
    return loose(TAG_RE.sub(" ", name))


def similar_name(a, b, threshold=0.7):
    """Один и тот же ник, прочитанный по-разному:
    - один — обрезанное начало другого (строка ленты ещё «выезжает»: «[722]» вместо «[722] Eskapist»);
    - один содержится в другом (OCR приклеил мусор: «[от] FLEX» и «FLEX»);
    - похожи по буквам — с тегом клана и без него."""
    na, nb = norm(a), norm(b)
    if min(len(na), len(nb)) >= 3 and (na.startswith(nb) or nb.startswith(na)):
        return True
    ca, cb = core_name(a), core_name(b)
    if min(len(ca), len(cb)) >= 3 and (ca in cb or cb in ca):
        return True
    return (same_player(a, b, threshold) or
            (ca and cb and difflib.SequenceMatcher(None, ca, cb).ratio() >= threshold))


def best_reading(values):
    """Из нескольких прочтений одного поля берём самое частое, при равенстве — самое похожее на остальные
    (а не самое длинное: длиннее обычно то, к чему OCR приклеил мусор, — «[17АтЈ Nikita»)."""
    values = [v for v in values if v not in ("", "?")] or values
    counts = Counter(values)

    def closeness(v):
        return sum(difflib.SequenceMatcher(None, norm(v), norm(o)).ratio() * n for o, n in counts.items())
    return max(counts, key=lambda v: (counts[v], closeness(v)))


class FeedReader:
    """Убийство висит в ленте несколько секунд, и за это время мы читаем его несколько раз.
    Все прочтения копим, а когда строка пропала из ленты (FINAL_AFTER секунд не видели), выдаём одно
    убийство с лучшим прочтением каждого поля."""

    def __init__(self, nick, templates_dir=None):
        self.nick = nick
        self.engine = make_engine("ru")
        self.templates = load_templates(templates_dir or resource("templates"))
        self.pending = []  # убийства, которые ещё видны в ленте: {"readings": [...], "first": t, "last": t}
        self.done = []     # недавно выданные — чтобы поздно всплывшее прочтение не стало новым убийством

    def _matches(self, kill, readings):
        # Если убийца совпал уверенно, ник жертвы сравниваем мягче: одного и того же игрока OCR может прочитать
        # совсем по-разному («SMG ] МасЕ-п—22-5.» и «[SMG]Mackan025»), а два разных убийства одним игроком
        # за пару секунд почти всегда — жертвы с совсем непохожими никами.
        for r in readings:
            if similar_name(r["killer"], kill["killer"], 0.85) and similar_name(r["victim"], kill["victim"], 0.5):
                return True
            if similar_name(r["killer"], kill["killer"]) and similar_name(r["victim"], kill["victim"]):
                return True
        return False

    def read(self, region: Image.Image, t: float):
        """region — область KILLFEED в масштабе 3440x1440. Возвращает убийства, которые окончательно ушли из ленты."""
        crop = ImageOps.grayscale(region)
        crop = crop.resize((crop.width * SCALE, crop.height * SCALE), Image.LANCZOS)

        for row in group_rows(recognize(self.engine, crop)):
            kill = parse_row(row)
            if kill is None:
                continue
            (x0, x1), (y0, y1) = kill["icon_x"], kill["y"]
            kill["icon"] = crop.crop((int(x0), int(y0), int(x1), int(y1)))
            kill["weapon"] = classify(kill["icon"], self.templates)
            group = next((g for g in self.pending if self._matches(kill, g["readings"])), None)
            if group:
                group["readings"].append(kill)
                group["last"] = t
            elif not any(t - d["last"] <= DEDUP_SECONDS and self._matches(kill, d["readings"]) for d in self.done):
                self.pending.append({"readings": [kill], "first": t, "last": t})
        return self._finalize(lambda g: t - g["last"] >= FINAL_AFTER)

    def flush(self):
        """Выдать всё накопленное (конец видео или сессии)."""
        return self._finalize(lambda g: True)

    def _finalize(self, ready):
        out = []
        for g in [g for g in self.pending if ready(g)]:
            self.pending.remove(g)
            self.done = [d for d in self.done if g["last"] - d["last"] <= DEDUP_SECONDS] + [g]
            rs = g["readings"]
            kill = {
                "t": g["first"],
                "killer": best_reading([r["killer"] for r in rs]),
                "victim": best_reading([r["victim"] for r in rs]),
                "weapon": best_reading([r["weapon"] for r in rs]),
                "distance_m": next((r["distance_m"] for r in rs if r["distance_m"] != ""), ""),
                "icon": max(rs, key=lambda r: r["icon"].width)["icon"],
                "readings": len(rs),
            }
            # «ты это или нет» — по всем прочтениям: хватит одного, где ник прочитан чисто
            killed = any(similar_name(r["killer"], self.nick, 0.8) for r in rs)
            died = any(similar_name(r["victim"], self.nick, 0.8) for r in rs)
            # ты и убийца, и жертва — самоубийство (разбился на вертолёте, своя граната): это смерть, не убийство
            kill["mine"] = "умер" if died else "убил" if killed else ""
            out.append(kill)
        return sorted(out, key=lambda k: k["t"])


def format_kill(k):
    dist = f" ({k['distance_m']} м)" if k["distance_m"] else ""
    return f"{k['time']:>6}  {k['killer']:<22} -[{k['weapon']}]-> {k['victim']}{dist}"
