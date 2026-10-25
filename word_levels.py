"""Сколько в процентах значат слова игры: «незначительное», «умеренное», «значительное».

Берёт data/attachments.json, сопоставляет каждую фразу плюсов/минусов с цифрой той же характеристики
и печатает разброс процентов для каждого уровня.
"""
import json
import re
from collections import defaultdict

# фраза в описании -> характеристика в таблице
STAT_WORDS = {
    "вертикальн": "Вертикальная отдача",
    "горизонтальн": "Горизонтальная отдача",
    "разброс": "Разброс",
    "прицеливания": "Время прицеливания",
    "экипировки": "Скорость экипировки",
}
LEVELS = {"незначительн": "незначительное", "умеренн": "умеренное", "значительн": "значительное"}


def level_of(phrase):
    p = phrase.lower()
    for stem, name in LEVELS.items():  # «незначительн» проверяется раньше «значительн»
        if p.startswith(stem):
            return name
    return None


def stat_of(phrase):
    p = phrase.lower()
    if "колебан" in p or "стабилизац" in p:
        return None  # раскачка прицела: на сайте цифр для неё нет
    return next((stat for word, stat in STAT_WORDS.items() if word in p), None)


def main():
    items = json.load(open("data/attachments.json", encoding="utf-8"))
    values = defaultdict(list)  # (характеристика, уровень) -> [проценты]
    for it in items:
        for phrase in it["pros"] + it["cons"]:
            level, stat = level_of(phrase), stat_of(phrase)
            raw = it["stats"].get(stat or "", "")
            m = re.match(r"([+\-]?\d+)%", raw)
            if level and m:
                values[(stat, level)].append(abs(int(m.group(1))))

    for stat in STAT_WORDS.values():
        print(stat)
        for level in LEVELS.values():
            v = sorted(values.get((stat, level), []))
            if v:
                print(f"  {level:<15} {v[0]:>3}–{v[-1]:<3}%   (обвесов: {len(v)}, типично {v[len(v) // 2]}%)")


if __name__ == "__main__":
    main()
