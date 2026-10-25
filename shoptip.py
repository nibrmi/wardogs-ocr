"""Находит подсказку предмета в магазине WARDOGS и определяет, какой это обвес.

Подсказка появляется рядом с курсором, поэтому её положение каждый раз разное. Опора — строки
«Плюсы:» / «Минусы:» / «Технические характеристики:»: они есть в каждой подсказке, а название
предмета лежит над ними на той же вертикали (выровнено по левому краю подсказки).

Проверка на кадрах:
    python shoptip.py <папка с кадрами f_*.jpg>
"""
import glob
import json
import os
import re
import sys
from difflib import SequenceMatcher

from PIL import Image, ImageOps

from winocr import make_engine, recognize

SEARCH = (0, 0, 3440, 1440)  # где искать подсказку при 3440x1440: весь экран (в инвентаре у рюкзака она справа)
TABS = (150, 15, 1700, 110)  # строка вкладок вверху (и заголовок «ОБЫСКИВАНИЕ») — по ним понимаем, какое меню открыто
MENU_WORDS = ("СНАРЯЖ", "ПРЕДМЕТ", "ОБЗОР", "РАССЫПН", "ИНВЕНТАР", "ТАБЛО", "ПРОГРЕСС", "ОБЫСК")
ANCHORS = ("Плюсы", "Минусы", "Технические")
WEIGHT_RE = re.compile(r"^\d+[,.]\d+\s*кг$")
SKIP_HEADERS = ("СЕЙЧАС ИСПОЛЬЗУЕТСЯ", "СОДЕРЖИТ")  # служебные строки над/под названием в инвентаре
ALIGN = 25        # насколько строки подсказки могут расходиться по левому краю (пиксели)
TITLE_GAP = 60    # максимум пустого места между строками названия и строкой типа

LOOSE = str.maketrans("аеорсухкмтвнзАЕОРСУХКМТВНЗ01il|", "aeopcyxkmtbh3aeopcyxkmtbh3oiiii")


def loose(s):
    """Ключ для нечёткого сравнения: регистр, похожие русские/латинские буквы и цифры сводим к одному виду."""
    return re.sub(r"[^a-zа-я0-9]", "", s.lower().translate(LOOSE))


def load_items(path=None):
    from paths import resource
    with open(path or resource("data", "attachments.json"), encoding="utf-8") as f:
        items = json.load(f)
    for it in items:
        it["_key"] = loose(it["name_ru"])
    return items


def find_tooltip(lines):
    """Возвращает (название, тип, (x, y) левого верхнего угла названия) или None, если подсказки на экране нет.

    Опора — «Плюсы:»/«Минусы:»/«Технические характеристики:». У магазинов патронов их нет, тогда опора —
    строка веса «0,31 кг» под строкой типа (в инвентаре вес стоит отдельной строкой у левого края подсказки)."""
    by_y = sorted(lines, key=lambda l: l["box"][1])
    # кандидаты в опору: сначала «Плюсы/Минусы», потом строки веса (их бывает несколько — например,
    # общий вес снаряжения в углу инвентаря), берём первый, над которым действительно есть подсказка
    # и последними — строки-пункты «- 60 Патронов» (у магазинов в магазине нет ни «Плюсов», ни отдельной строки веса)
    candidates = [l for l in by_y if l["text"].lstrip("- ").startswith(ANCHORS)] + \
                 [l for l in by_y if WEIGHT_RE.match(l["text"].strip())] + \
                 [l for l in by_y if re.match(r"^\s*[-–]\s*\S", l["text"])]
    for anchor in candidates:
        tip = tooltip_above(lines, anchor)
        if tip:
            return tip
    return None


def tooltip_above(lines, anchor):
    """Название и тип над опорной строкой, выровненные по её левому краю."""
    ax, ay = anchor["box"][0], anchor["box"][1]
    above = sorted((l for l in lines if abs(l["box"][0] - ax) <= ALIGN and l["box"][1] < ay
                    and not WEIGHT_RE.match(l["text"].strip())          # вес между типом и опорой
                    and not l["text"].lstrip().startswith("-")           # строки-пункты
                    and not l["text"].strip().upper().startswith(SKIP_HEADERS)), key=lambda l: l["box"][1])
    if not above:
        return None
    # снизу вверх: сразу над якорем — строка типа («ДУЛО», «ОПТИКА»), над ней одна-две строки названия
    block = [above[-1]]
    for l in reversed(above[:-1]):
        if block[0]["box"][1] - l["box"][3] > TITLE_GAP:
            break
        block.insert(0, l)
    if len(block) < 2:
        return None
    kind = block[-1]["text"]
    title = " ".join(l["text"] for l in block[:-1])
    # вес: в магазине — справа в строке типа, в инвентаре — отдельной строкой под типом
    top, bottom = block[0]["box"][1], anchor["box"][3] + 40
    weight = next((m.group(1) for l in lines if top <= l["box"][1] <= bottom and ax - ALIGN <= l["box"][0] <= ax + 900
                   for m in [re.search(r"(\d+[,.]\d+)\s*кг", l["text"])] if m), None)
    return title, kind, (block[0]["box"][0], block[0]["box"][1]), weight


def kg(text):
    m = re.search(r"(\d+)[,.](\d+)", text or "")
    return float(f"{m.group(1)}.{m.group(2)}") if m else None


def match(title, items, weight=None, threshold=0.6):
    """Ищет обвес по названию. Названия бывают почти одинаковые («20-зарядный магазин для STANAG» и «…для FAL»),
    поэтому, если в подсказке прочитался вес, обвесы с другим весом сильно штрафуем.
    Возвращает (обвес, похожесть) или (None, лучшая похожесть)."""
    key, w = loose(title), kg(weight)
    best, score = None, 0.0
    for it in items:
        s = SequenceMatcher(None, key, it["_key"]).ratio()
        iw = kg(it["stats"].get("Вес"))
        if w is not None and iw is not None and abs(iw - w) > 0.005:
            s -= 0.3
        if s > score:
            best, score = it, s
    return (best, score) if score >= threshold else (None, score)


class ShopTip:
    def __init__(self):
        self.engine = make_engine("ru")
        self.items = load_items()

    def tabs_text(self, screen: Image.Image):
        """Текст строки вкладок вверху экрана: по нему видно, какое меню открыто (магазин, инвентарь, итоги)."""
        return " ".join(l["text"] for l in recognize(self.engine, ImageOps.grayscale(screen.crop(TABS))))

    def shop_open(self, screen: Image.Image, tabs=None):
        """Открыт ли магазин или инвентарь: «ОБЗОР / СНАРЯЖЕНИЕ / ПРЕДМЕТЫ» или «ИНВЕНТАРЬ / ТАБЛО / ПРОГРЕСС»."""
        text = self.tabs_text(screen) if tabs is None else tabs
        return any(w in text for w in MENU_WORDS)

    def read(self, screen: Image.Image, tabs=None):
        """screen — область SEARCH кадра (в масштабе 3440x1440). Возвращает
        {"title", "kind", "pos", "item", "score"} или None. pos — угол названия в координатах кадра."""
        if screen.size != (SEARCH[2] - SEARCH[0], SEARCH[3] - SEARCH[1]):
            screen = screen.crop(SEARCH)
        self.last_lines = []
        if not self.shop_open(screen, tabs):
            return None
        self.last_lines = recognize(self.engine, ImageOps.grayscale(screen))  # пригодятся для сборок (builds.py)
        tip = find_tooltip(self.last_lines)
        if tip is None:
            return None
        title, kind, pos, weight = tip
        item, score = match(title, self.items, weight)
        return {"title": title, "kind": kind, "pos": pos, "weight": weight, "item": item, "score": score}


def main():
    st = ShopTip()
    for path in sorted(glob.glob(os.path.join(sys.argv[1], "f_*.jpg"))):
        r = st.read(Image.open(path))
        if r:
            name = r["item"]["name_ru"] if r["item"] else "— нет в таблице"
            print(f"{os.path.basename(path)}  «{r['title']}» [{r['kind']}]  ->  {name}  ({r['score']:.2f})")


if __name__ == "__main__":
    main()
