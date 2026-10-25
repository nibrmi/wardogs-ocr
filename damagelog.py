"""Читает журнал урона WARDOGS (вкладка «Нанесенный ущерб») со скриншота и считает статистику.

Использование:
    python damagelog.py <скриншот> [<скриншот> ...]

Журнал — это игровой лог боя: каждое попадание с оружием, патроном, уроном, частью тела, дистанцией и бронёй,
плюс строки «убит игрок». Текст чистый, на тёмном фоне — OCR читает его гораздо надёжнее, чем ленту убийств.
"""
import re
import sys
from collections import Counter, defaultdict

from PIL import Image, ImageOps

from feedreader import clean_name
from winocr import make_engine, recognize

# OCR путает похожие буквы в цифрах и единицах: «т» вместо «m», «З» вместо «3», «О» вместо «0»
DIGITS = str.maketrans("ЗзОоlI", "330011")

HIT_RE = re.compile(
    r"\[(?P<time>\d\d:\d\d:\d\d)\]\s*(?P<shooter>.+?),\s*(?P<weapon>.+?)\s*\((?P<ammo>[^)]*)\):\s*"
    r"нанесено\s*(?P<dmg>[\dЗО,.]+)\s*ед\.?\s*урона\s*игроку\s*(?P<victim>.+?)\s*\((?P<part>[^)]+)\)\s*"
    r"с\s*(?P<dist>[\dЗО]+)\s*[тmм]\b"
)
ARMOR_RE = re.compile(r"(?P<kind>Броня|Шлем)\s*(?P<lvl>\d)-го\s*уровня\s*поглотила\s*(?P<abs>[\dЗО,.]+)")
KILL_RE = re.compile(r"(?P<shooter>[^:\]]+?):\s*убит\s*игрок\s*(?P<victim>.+?)\.?$")


def number(s):
    return float(s.translate(DIGITS).replace(",", "."))


def read_lines(path, engine):
    img = ImageOps.grayscale(Image.open(path).convert("RGB"))
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    return [l["text"] for l in recognize(engine, img)]


LOOSE = str.maketrans("аеорсухкмтвнзАЕОРСУХКМТВНЗ01il|", "aeopcyxkmtbh3aeopcyxkmtbh3oiiii")


def loose_key(name):
    """Ключ для сравнения ников, устойчивый к ошибкам OCR: «те1оп15З9» и «melon1539» дают похожие ключи."""
    return re.sub(r"[^a-z0-9]", "", clean_name(name).lower().translate(LOOSE))


def same_victim(a, b):
    from difflib import SequenceMatcher
    ka, kb = loose_key(a), loose_key(b)
    return bool(ka and kb) and (ka in kb or kb in ka or SequenceMatcher(None, ka, kb).ratio() >= 0.6)


def nicest(names):
    """Из разных прочтений ника берём самое «латинское» (ники в основном латиницей) и самое частое."""
    counts = Counter(names)
    return max(counts, key=lambda n: (sum(c.isascii() for c in n), counts[n], len(n)))


def parse(lines):
    hits, kills = [], []
    since_kill = []  # попадания после предыдущей строки «убит» — по ним считаем, сколько ушло на убийство
    for line in lines:
        m = HIT_RE.search(line)
        if m:
            armor = ARMOR_RE.search(line)
            hits.append({
                "time": m["time"], "shooter": m["shooter"].strip(), "weapon": m["weapon"].strip(),
                "ammo": m["ammo"].strip(), "damage": number(m["dmg"]), "victim": clean_name(m["victim"]),
                "part": m["part"].strip(), "distance": int(number(m["dist"])),
                "armor": f"{armor['kind']} {armor['lvl']}" if armor else "", "absorbed": number(armor["abs"]) if armor else 0.0,
            })
            since_kill.append(hits[-1])
            continue
        m = KILL_RE.search(line)
        if m:
            victim = clean_name(m["victim"])
            on_victim = [h for h in since_kill if same_victim(h["victim"], victim)]
            name = nicest([h["victim"] for h in on_victim] + [victim])
            for h in on_victim:
                h["victim"] = name  # одно имя для всех прочтений
            kills.append({"shooter": clean_name(m["shooter"]), "victim": name, "hits": len(on_victim),
                          "damage": sum(h["damage"] for h in on_victim)})
            since_kill = [h for h in since_kill if h not in on_victim]
    return hits, kills


def summary(hits, kills):
    print(f"Попаданий: {len(hits)}, урона нанесено: {sum(h['damage'] for h in hits):.0f}, "
          f"броня поглотила: {sum(h['absorbed'] for h in hits):.0f}")
    print(f"Убийств: {len(kills)} — " + ", ".join(k["victim"] for k in kills))

    parts = Counter(h["part"] for h in hits)
    print("Куда попадал:", ", ".join(f"{p} {n} ({n * 100 // len(hits)}%)" for p, n in parts.most_common()))

    by_weapon = defaultdict(list)
    for h in hits:
        by_weapon[f"{h['weapon']} ({h['ammo']})"].append(h)
    for w, hs in by_weapon.items():
        avg = sum(h["damage"] for h in hs) / len(hs)
        print(f"{w}: попаданий {len(hs)}, средний урон {avg:.1f}, дистанция {min(h['distance'] for h in hs)}–{max(h['distance'] for h in hs)} м")

    for k in kills:
        print(f"  {k['victim']}: попаданий до убийства {k['hits']}, урона {k['damage']:.0f}")


def main():
    engine = make_engine("ru")
    lines = [line for path in sys.argv[1:] for line in read_lines(path, engine)]
    hits, kills = parse(lines)
    summary(hits, kills)


if __name__ == "__main__":
    main()
