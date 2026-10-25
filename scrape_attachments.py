"""Собирает таблицу обвесов с wardogs.zone: русское и английское название, цена, вес, все цифры и словесные плюсы/минусы.

Использование:
    python scrape_attachments.py            # результат: data/attachments.csv и data/attachments.json

Страницы кешируются в data/cache/, поэтому повторный запуск ничего не скачивает заново.
Чтобы обновить данные после патча игры, удали data/cache/.
Скачиваем вежливо: одна страница в секунду, только разрешённые robots.txt разделы (/database/, не /api/).
Цифры — с фанатского сайта, не официальные: после патчей они могут отставать от игры.
"""
import csv
import json
import os
import re
import subprocess
import time
from html import unescape

BASE = "https://wardogs.zone"
CACHE = os.path.join("data", "cache")
VALUE_RE = re.compile(r"^[+\-−]?\d[\d\s,.]*\s*(%|кг|x|х|м/с|об/мин|°)?$")


def fetch(path):
    """Скачивает страницу (или берёт из кеша)."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, path.strip("/").replace("/", "_") + ".html")
    if os.path.exists(cached):
        with open(cached, encoding="utf-8") as f:
            return f.read()
    # Через curl: стандартный клиент Python сайт отсекает (403), а robots.txt эти страницы разрешает
    result = subprocess.run(["curl.exe", "-s", "-f", "--max-time", "30", BASE + path], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"не скачалось {path}: curl вернул {result.returncode}")
    html = result.stdout.decode("utf-8")
    with open(cached, "w", encoding="utf-8") as f:
        f.write(html)
    time.sleep(1.0)
    return html


def text_tokens(html):
    """Превращает HTML в список кусочков видимого текста."""
    html = re.sub(r"(?s)<(script|style|svg).*?</\1>", "", html)
    parts = (unescape(p).strip() for p in re.split(r"<[^>]+>", html))
    return [p for p in parts if p]


def list_cards(html):
    """Карточки на странице списка: id -> (название, класс)."""
    cards = {}
    for chunk in html.split('class="group relative flex flex-col')[1:]:
        m = re.search(r'aria-label="([^"]+)"[^>]*href="(?:/ru)?/database/([a-z0-9_]+)"', chunk)
        if not m:
            continue
        name, item_id = unescape(m.group(1)), m.group(2)
        cls = re.search(r"</div><div[^>]*><span[^>]*>([^<]+)</span><span title=", chunk)
        cards[item_id] = (name, unescape(cls.group(1)) if cls else "")
    return cards


def between(tokens, start, stop):
    try:
        i = tokens.index(start) + 1
    except ValueError:
        return []
    j = next((k for k in range(i, len(tokens)) if tokens[k] in stop), len(tokens))
    return tokens[i:j]


def parse_detail(html):
    tokens = text_tokens(html)
    item = {}
    price = between(tokens, "База данных", {"Стоимость"})
    item["price"] = next((t for t in reversed(price) if t.startswith("$")), "")

    # «Спецификация»: пары «название | значение»; строки без значения (вроде «Управляемость») — заголовки групп
    spec = between(tokens, "Спецификация", {"Описание", "Подходит", "Похожее"})
    stats = {}
    for label, value in zip(spec, spec[1:]):
        if not VALUE_RE.match(label) and VALUE_RE.match(value):
            stats[label] = value.replace("−", "-")
    item["stats"] = stats
    item["pros"] = between(tokens, "Плюсы:", {"Минусы:", "Подходит", "Похожее", "Справка"})
    item["cons"] = between(tokens, "Минусы:", {"Подходит", "Похожее", "Справка"})

    fits = between(tokens, "Подходит", {"Похожее", "Справка"})
    item["fits"] = fits[1::2] if fits and fits[0].isdigit() else []  # число, потом пары «оружие | класс»
    return item


# Заведомо не обвесы: патроны, техника, снаряжение. Отсекаем, чтобы не качать лишние страницы.
NOT_ATTACHMENT = re.compile(
    r"^(weapons|vehicles|attachments|ammo|equipment|compare)$|^(land|air|stationary)-|tracer|hollowpoint|armou?rpiercing"
    r"|armor|helmet|backpack|tacvest|pouch|grenade|bandage|medkit|stim|defib|resusc|enox|parachute|repairtool|buildtool"
    r"|supply|supplies|crate|fuel|battery|arrow|mine|claymore|crowbar|c4|ied|molotov|flares|binoc|monocular|rangefinder"
    r"|fob|smoke|loudspeaker|projectile|^\d+(x\d+)?mm$|^\d+(acp|win|colt|cal|ae|nor|g-)")


def page_title_name(html):
    """Название предмета из заголовка страницы: «Название: WARDOGS …»."""
    m = re.search(r"<title>([^<]+)</title>", html)
    return unescape(m.group(1)).split(": WARDOGS")[0].strip() if m else ""


def main():
    sitemap = fetch("/sitemap.xml")
    slugs = list(dict.fromkeys(re.findall(r"<loc>https://wardogs\.zone/database/([^<\"/?]+)</loc>", sitemap)))
    candidates = [s for s in slugs if not NOT_ATTACHMENT.search(s)]
    print(f"предметов в sitemap: {len(slugs)}, проверяю как возможные обвесы: {len(candidates)}")

    items = []
    for n, slug in enumerate(candidates, 1):
        html_ru = fetch(f"/ru/database/{slug}")
        tokens = text_tokens(html_ru)
        spec = between(tokens, "Спецификация", {"Описание"})
        # обвесы — класс «Модуль»; стандартные магазины сайт относит к «Боеприпасам», узнаём их по «mag» в адресе
        is_module = spec[:2] == ["Класс", "Модуль"]
        is_magazine = spec[:2] == ["Класс", "Боеприпасы"] and "mag" in slug
        if not (is_module or is_magazine):
            continue  # оружие, патроны, техника и т.п.
        name_en = page_title_name(fetch(f"/database/{slug}"))
        items.append({"id": slug, "name_ru": page_title_name(html_ru), "name_en": name_en, "class": "", **parse_detail(html_ru)})
        if n % 20 == 0:
            print(f"  {n}/{len(candidates)}, обвесов: {len(items)}")

    os.makedirs("data", exist_ok=True)
    with open(os.path.join("data", "attachments.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)

    stat_names = sorted({k for it in items for k in it["stats"]})
    with open(os.path.join("data", "attachments.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name_ru", "name_en", "class", "price"] + stat_names + ["pros", "cons"])
        for it in items:
            w.writerow([it["id"], it["name_ru"], it["name_en"], it["class"], it["price"]]
                       + [it["stats"].get(s, "") for s in stat_names]
                       + ["; ".join(it["pros"]), "; ".join(it["cons"])])
    print(f"готово: {len(items)} обвесов, характеристики: {', '.join(stat_names)}")


if __name__ == "__main__":
    main()
