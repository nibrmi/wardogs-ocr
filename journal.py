"""Журнал урона WARDOGS (экран смерти, кнопка B): читает строки с кадров, склеивает и разбирает.

Журнал накопительный за весь матч и содержит всё: нанесённый и полученный урон, убийства, лечение, деньги.
Видна только последняя часть (прокрутка), поэтому строки со всех кадров склеиваем без повторов.

Использование:
    python journal.py <папка с кадрами *.jpg 3440x1440>   # печатает сводку и пишет out/journal.csv
"""
import csv
import glob
import os
import re
import sys
from collections import Counter, defaultdict

from PIL import Image, ImageOps

from damagelog import ARMOR_RE, HIT_RE, KILL_RE, number
from feedreader import clean_name
from winocr import make_engine, recognize

BOX = (850, 240, 2600, 1110)  # окно журнала при 3440x1440 (вместе со строкой вкладок)
TABS_STRIP = (850, 245, 2600, 310)  # только строка вкладок — для быстрой проверки, открыт ли журнал
TABS_WORDS = ("УЩЕРБ", "ЛЕЧЕНИЕ", "ДЕНЬГИ")
TIME_RE = re.compile(r"^\s*\[?(\d\d:\d\d:\d\d)\]?\s*(.*)$")
MONEY_RE = re.compile(r"^(?P<what>.+?)\s*[-–—]?\s*\$\s*(?P<amount>[\d\sЗО]+)$")
NO_TIME_RE = re.compile(r"убит игрок|оживлен игрок|возродился")
ROW_TOLERANCE = 12 # куски строки, чьи центры ближе (в увеличенных пикселях), — одна строка журнала

# Известные виды денежных начислений (из журналов). Новый вид, которого тут нет, попадёт в «Другое: …» —
# увидишь его в статистике и допишешь сюда.
MONEY_REASONS = ["Присутствие в Control Zone", "Присутствие в Hot Zone", "Вход в Control Zone", "Вход в Hot Zone",
                 "Тактическая высадка", "Тактическая высадка из вызываемого транспорта", "Пассажир выжил",
                 "Помощь высаженному игроку", "Убийство", "Помощь в убийстве", "Ждал оживления", "Заправка транспорта",
                 "Оживление", "Лечение", "Ремонт транспорта"]

# Названия оружия в журнале — чтобы «Ga1il», «Gali1», «КН-2002» свести к одному виду
WEAPONS = ["АК-74", "Galil", "KH-2002", "A-91", "M4", "T-21", "TCX-SPR", "FAL", "Bushmaster M17S", "AMP-9", "MP5",
           "ПП-19 «Витязь»", "ПП-19 «Бизон»", "Super-45", "Evo-3 Ultra", "M249 SAW", "ПКМ", "BMR-308", "M14", "СКС",
           "СВД", "AMR-50", "MK22", "Mosin-Nagant", "Scout Rifle TD", "SV-98", "M500", "MP-43", "Deagle", "GGX-17",
           "GGX-18", "M1911", "The Judge", "Compound Bow", "RPG-7", "MAAWS", "MGL-40"]


def journal_open(lines):
    text = " ".join(l["text"] for l in lines)
    return sum(w in text for w in TABS_WORDS) >= 2


def is_open(engine, frame):
    """Быстрая проверка по узкой полоске со вкладками «НАНЕСЕННЫЙ УЩЕРБ / … / ДЕНЬГИ».
    Журнал стоит по центру экрана, поэтому на экранах другой ширины полоску сдвигаем (layout.centered)."""
    from layout import centered
    return journal_open(recognize(engine, ImageOps.grayscale(frame.crop(centered(TABS_STRIP, frame.width)))))


def read_frame(engine, frame):
    """Строки журнала с одного кадра 3440x1440 (картинка или путь к файлу): [(время, текст), ...] или None.
    (Яркий канал, как на экране итогов, здесь хуже: знак «$» перед зелёной суммой начинает читаться как «31».)"""
    from layout import centered
    if isinstance(frame, str):
        frame = Image.open(frame)
    img = ImageOps.grayscale(frame.crop(centered(BOX, frame.width)))
    lines = recognize(engine, img.resize((img.width * 2, img.height * 2), Image.LANCZOS))
    if not journal_open(lines):
        return None
    # OCR рвёт строку журнала на куски (сумма зелёным — отдельный кусок): склеиваем куски на одной высоте
    rows = []
    for l in sorted(lines, key=lambda l: (l["box"][1] + l["box"][3]) / 2):
        cy = (l["box"][1] + l["box"][3]) / 2
        if rows and abs(rows[-1][0] - cy) <= ROW_TOLERANCE:
            rows[-1][1].append(l)
        else:
            rows.append([cy, [l]])
    out, last_time = [], None
    for _, parts in rows:
        text = " ".join(p["text"] for p in sorted(parts, key=lambda p: p["box"][0]))
        m = TIME_RE.match(text)
        if m and len(m.group(2)) > 3:
            last_time = m.group(1)
            out.append((last_time, m.group(2).strip()))
        elif last_time and NO_TIME_RE.search(text):
            # перед «убит игрок» стоит значок черепа, и OCR теряет вместе с ним время — берём время строки выше
            out.append((last_time, text.strip()))
    return out


def parsable(text):
    return bool(HIT_RE.search("[00:00:00] " + text) or KILL_RE.search(text) or MONEY_RE.match(text))


def merge(frames):
    """Склейка без повторов. Одна строка на разных кадрах читается чуть по-разному («нанесено» / «нанесе о»),
    поэтому внутри каждой секунды похожие строки считаем одной строкой (нечёткое сравнение). Сколько раз она
    встречается — берём наибольшее число на одном кадре (две одинаковые высадки в одну секунду бывают на самом деле),
    а текст — лучшее прочтение: то, что разбирается, и чаще встречается."""
    from difflib import SequenceMatcher

    from shoptip import loose

    clusters = defaultdict(list)  # время -> [{"key", "variants": Counter, "max": n}]
    for lines in frames:
        per_frame = Counter()
        for t, text in lines:
            key = loose(text)
            group = next((c for c in clusters[t] if SequenceMatcher(None, key, c["key"]).ratio() >= 0.85), None)
            if group is None:
                group = {"key": key, "variants": Counter(), "max": 0}
                clusters[t].append(group)
            group["variants"][text] += 1
            per_frame[id(group)] += 1
        for t in {t for t, _ in lines}:
            for c in clusters[t]:
                c["max"] = max(c["max"], per_frame[id(c)])
    out = []
    for t in sorted(clusters):
        for c in clusters[t]:
            text = max(c["variants"], key=lambda v: (parsable(v), c["variants"][v], len(v)))
            out += [(t, text)] * c["max"]
    return out


def drop_repeated_kills(rows, window=60):
    """Строки «убит игрок» без своего времени получают время соседней строки, а оно на разных кадрах разное —
    одно и то же убийство может попасть в соседние секунды. Повтор в пределах window секунд выкидываем."""
    from shoptip import loose

    def sec(t):
        h, m, s = map(int, t.split(":"))
        return h * 3600 + m * 60 + s

    out, seen = [], []
    for r in rows:
        if r["type"] in ("убил", "убит"):
            key = (loose(r["who"]), loose(r["whom"]))
            if any(k == key and abs(sec(r["time"]) - s) <= window for k, s in seen):
                continue
            seen.append((key, sec(r["time"])))
        out.append(r)
    return out


def canon_reason(text):
    """Начисление денег — только из известного списка; непохожее не выдумываем, а помечаем «Другое: …»."""
    from difflib import SequenceMatcher

    from shoptip import loose
    key = loose(text)
    best = max(MONEY_REASONS, key=lambda r: SequenceMatcher(None, key, loose(r)).ratio())
    return best if SequenceMatcher(None, key, loose(best)).ratio() >= 0.85 else f"Другое: {text}"


def canon_weapon(name):
    from difflib import SequenceMatcher

    from shoptip import loose
    key = loose(name)
    best = max(WEAPONS, key=lambda w: SequenceMatcher(None, key, loose(w)).ratio())
    return best if SequenceMatcher(None, key, loose(best)).ratio() >= 0.7 else name


def classify(time, text, nick):
    """Тип строки и её поля."""
    line = f"[{time}] {text}"
    m = HIT_RE.search(line)
    if m:
        armor = ARMOR_RE.search(line)
        shooter, victim = clean_name(m["shooter"]), clean_name(m["victim"])
        return {"time": time, "type": "урон нанесён" if nick.lower() in shooter.lower() else "урон получен",
                "who": shooter, "whom": victim, "weapon": canon_weapon(m["weapon"].strip()), "ammo": m["ammo"].strip(),
                "part": m["part"].strip(), "value": number(m["dmg"]), "distance": int(number(m["dist"])),
                "absorbed": number(armor["abs"]) if armor else 0.0}
    m = KILL_RE.search(text)
    if m:
        shooter, victim = clean_name(m["shooter"]), clean_name(m["victim"])
        return {"time": time, "type": "убил" if nick.lower() in shooter.lower() else "убит",
                "who": shooter, "whom": victim}
    # «- $125» OCR иногда читает как «-31 125» или «-61 125»: знак доллара принят за цифры
    m = MONEY_RE.match(re.sub(r"\s*[-–—]\s*[36]1?\s+(?=\d)", " - $", text))
    if m:
        return {"time": time, "type": "деньги", "what": canon_reason(m["what"].strip(" -–—¯")),
                "value": number(m["amount"].replace(" ", ""))}
    return {"time": time, "type": "прочее", "what": text}


FIELDS = ["time", "type", "who", "whom", "what", "weapon", "ammo", "part", "value", "distance", "absorbed"]


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def summary(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["type"]].append(r)

    money = by["деньги"]
    print(f"Деньги: {sum(r['value'] for r in money):,.0f} $ за {len(money)} начислений".replace(",", " "))
    totals = defaultdict(float)
    counts = Counter()
    for r in money:
        totals[r["what"]] += r["value"]
        counts[r["what"]] += 1
    for what, total in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {total:>8,.0f} $  {what} (×{counts[what]})".replace(",", " "))

    dealt, got = by["урон нанесён"], by["урон получен"]
    print(f"Урон нанесён: {sum(r['value'] for r in dealt):.0f} за {len(dealt)} попаданий; "
          f"получен: {sum(r['value'] for r in got):.0f} за {len(got)} попаданий")
    if dealt:
        print("  Твоё оружие:", ", ".join(f"{w} — {n} попад." for w, n in Counter(r["weapon"] for r in dealt).most_common()))
        print("  Куда попадал:", ", ".join(f"{p} {n}" for p, n in Counter(r["part"] for r in dealt).most_common()))
    if got:
        print("  Кто попадал в тебя:", ", ".join(f"{w} ({wp}) {n}" for (w, wp), n in
                                                 Counter((r["who"], r["weapon"]) for r in got).most_common(5)))
    print(f"Убийств: {len(by['убил'])} — " + ", ".join(r["whom"] for r in by["убил"]))
    print(f"Смертей: {len(by['убит'])} — от " + ", ".join(r["who"] for r in by["убит"]))
    other = by["прочее"]
    if other:
        print(f"Не разобрано строк: {len(other)}, например: " + " | ".join(r["what"] for r in other[:5]))


def main():
    folder, nick = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "Nikita")
    engine = make_engine("ru")
    frames = []
    for path in sorted(glob.glob(os.path.join(folder, "*.jpg"))):
        lines = read_frame(engine, path)
        if lines:
            frames.append(lines)
    print(f"кадров с журналом: {len(frames)}")
    rows = drop_repeated_kills([classify(t, text, nick) for t, text in merge(frames)])
    os.makedirs("out", exist_ok=True)
    write_csv(rows, os.path.join("out", "journal.csv"))
    print(f"строк журнала: {len(rows)} (out/journal.csv)\n")
    summary(rows)


if __name__ == "__main__":
    main()
