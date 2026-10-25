"""Язык интерфейса программы: русский или английский. / Program UI language: Russian or English.

    from i18n import t, set_lang
    t("start")            -> «▶  Старт» или «▶  Start»
    t("saved_to", path=p) -> подстановка параметров

Язык самой игры выбирать не нужно: распознавание понимает надписи игры на обоих языках.
"""
import locale

LANG = "ru"

STATS_EN = {"Вес": "Weight", "Вертикальная отдача": "Vertical recoil", "Горизонтальная отдача": "Horizontal recoil",
            "Разброс": "Spread", "Время прицеливания": "ADS time", "Скорость экипировки": "Equip speed", "Масштаб": "Zoom"}

TEXTS = {
    # окно программы
    "nick": ("Твой ник в игре:", "Your in-game nickname:"),
    "what": ("Что делать", "Features"),
    "tips": ("Подсказки с цифрами обвесов (магазин, инвентарь)", "Real attachment numbers (shop, inventory)"),
    "builds": ("Итог сборки оружия (инвентарь, обыск; веса — клавиша F)", "Weapon build totals (inventory, looting; show weights with F)"),
    "killfeed": ("Трекер убийств по ленте", "Kill feed tracker"),
    "journal": ("Журнал урона на экране смерти (кнопка B)", "Damage log on the death screen (key B)"),
    "endscreen": ("Итоги матча (победа/поражение, деньги)", "Match results (victory/defeat, money)"),
    "shots": ("Сохранять снимки ленты для разбора (~30 МБ за 20 минут)", "Save kill feed snapshots for debugging (~30 MB per 20 min)"),
    "load": ("Нагрузка", "Load"),
    "tick": ("Проверять экран каждые {s:.1f} с", "Check the screen every {s:.1f} s"),
    "tick_hint": ("Реже — меньше нагрузка на процессор, но подсказки появляются с задержкой и короткие строки ленты могут пропасть.",
                  "Less often = lower CPU load, but hints appear later and short kill feed lines may be missed."),
    "language": ("Язык программы:", "Program language:"),
    "start": ("▶  Старт", "▶  Start"),
    "stop": ("■  Стоп", "■  Stop"),
    "stats": ("Статистика", "Statistics"),
    "data_folder": ("Папка с данными", "Data folder"),
    "stopped": ("Остановлено", "Stopped"),
    "stopping": ("Останавливаю…", "Stopping…"),
    "running": ("Работает", "Running"),
    "need_nick": ("Впиши свой ник в игре — по нему трекер узнаёт твои убийства и смерти.",
                  "Enter your in-game nickname — the tracker uses it to find your kills and deaths."),
    "saved_to": ("Данные сохраняются в {path}", "Data is saved to {path}"),
    "credits": ("Цифры обвесов — wardogs.zone (с разрешения автора). Код: github.com/nibrmi/wardogs-ocr",
                "Attachment numbers — wardogs.zone (with the owner's permission). Code: github.com/nibrmi/wardogs-ocr"),
    "restart_lang": ("Язык поменяется после перезапуска программы.", "The language will change after restarting the program."),
    "no_ocr": ("В Windows не найдено распознавание текста для русского языка.\n\n"
               "Как поставить: Параметры → Время и язык → Язык и регион → Добавить язык → Русский "
               "(достаточно базовых компонентов), затем перезапустить программу.\n\nПодробности: {e}",
               "Windows text recognition (OCR) for Russian is not installed — the program needs it even for the English game "
               "(it reads both alphabets).\n\nHow to install: Settings → Time & language → Language & region → Add a language → "
               "Russian (basic features are enough), then restart the program.\n\nDetails: {e}"),
    # окошки поверх игры
    "only_weight": ("цифр нет — только вес", "no numbers — weight only"),
    "price": ("Цена {p}", "Price {p}"),
    "data_src": ("данные: wardogs.zone", "data: wardogs.zone"),
    "not_in_table": ("Нет в таблице:\n{t}", "Not in the table:\n{t}"),
    "build_title": ("Сборка {w} — итог", "{w} build — total"),
    "not_identified": ("модули не опознаны", "attachments not identified"),
    "not_found": ("нет в таблице", "not in the table"),
    "build_note": ("≈ эффекты перемножены; цифры — wardogs.zone", "≈ effects multiplied; numbers — wardogs.zone"),
    "slot_magazine": ("Магазин", "Magazine"), "slot_optic": ("Прицел", "Optic"),
    "slot_underbarrel": ("Подствол", "Underbarrel"), "slot_muzzle": ("Дуло", "Muzzle"),
    # терминал / журнал сессии
    "writing": ("Пишу в {path}.csv. Ctrl+C — остановить и показать итоги.", "Writing to {path}.csv. Ctrl+C — stop and show the summary."),
    "kill": ("УБИЛ", "KILL"), "death": ("УМЕР", "DEATH"),
    "wait_game": ("Жду окно WARDOGS…", "Waiting for the WARDOGS window…"),
    "minimized": ("Игра свёрнута — пауза.", "Game minimized — paused."),
    "working": ("Игра найдена — работаю.", "Game found — working."),
    "journal_open": ("Журнал урона открыт — читаю.", "Damage log open — reading."),
    "alive": ("Работаю: прочитано снимков ленты {n}, убийств записано {k}.", "Working: {n} kill feed snapshots read, {k} kills recorded."),
    "match": ("Итоги матча: {r}, прибыль {p}, заработано {e}, потрачено {s}", "Match result: {r}, profit {p}, earned {e}, spent {s}"),
    "sum_title": ("=== Итоги сессии ({nick}) ===", "=== Session summary ({nick}) ==="),
    "sum_total": ("Убийств в ленте всего: {n}", "Kills in the feed: {n}"),
    "sum_kd": ("Ты убил: {k}, умер: {d}", "You killed: {k}, died: {d}"),
    "sum_weapons": ("Твоё оружие:", "Your weapons:"),
    "sum_longest": ("Самое дальнее убийство: {m} м", "Longest kill: {m} m"),
    "sum_killed_by": ("Тебя убивали из:", "You were killed with:"),
    "sum_nemesis": ("Чаще всех тебя убивал:", "Killed you the most:"),
}


def set_lang(lang):
    global LANG
    LANG = "en" if lang == "en" else "ru"


def default_lang():
    """По языку Windows: русская система — русский, иначе английский."""
    try:
        code = locale.getlocale()[0] or locale.getdefaultlocale()[0] or ""
    except (ValueError, TypeError):
        code = ""
    return "ru" if code.lower().startswith(("ru", "russian")) else "en"


def t(key, **kw):
    ru, en = TEXTS[key]
    text = en if LANG == "en" else ru
    return text.format(**kw) if kw else text


def stat(name):
    """Название характеристики в языке интерфейса (данные хранятся с русскими названиями)."""
    return STATS_EN.get(name, name) if LANG == "en" else name


def item_name(item):
    return (item.get("name_en") or item["name_ru"]) if LANG == "en" else item["name_ru"]


def value(v):
    """«0,13 кг» -> «0.13 kg» для английского."""
    return v.replace(",", ".").replace("кг", "kg").replace("х", "x") if LANG == "en" else v
