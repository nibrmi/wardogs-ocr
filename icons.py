"""Работа с иконками из ленты убийств.

Вырезка между ником убийцы и ником жертвы содержит: [иконка оружия] [значок: череп, взрыв…] [дистанция].
Здесь мы отделяем иконку оружия от остального и приводим её к одному размеру, чтобы иконки можно было сравнивать.
"""
import numpy as np
from PIL import Image

BRIGHT = 150      # пиксели ярче этого считаем частью иконки (иконки белые, фон тёмный или пёстрый)
MIN_GAP = 12      # пустых столбцов между иконкой оружия и следующим значком (в увеличенных пикселях)
MIN_WIDTH = 40    # уже этого — не иконка, а шум или хвостик ника вроде «ツ»
SIZE = (96, 32)   # к этому размеру приводим все иконки


def split_blobs(img: Image.Image):
    """Делит вырезку на отдельные значки по пустым столбцам. Возвращает [(x0, x1), ...] слева направо."""
    a = np.asarray(img.convert("L")) > BRIGHT
    cols = a.sum(axis=0) >= 2  # столбец «занят», если в нём хотя бы 2 ярких пикселя
    blobs, start, gap = [], None, 0
    for x, filled in enumerate(cols):
        if filled:
            if start is None:
                start = x
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= MIN_GAP:
                blobs.append((start, x - gap + 1))
                start, gap = None, 0
    if start is not None:
        blobs.append((start, len(cols) - gap))
    return [b for b in blobs if b[1] - b[0] >= MIN_WIDTH]


def normalize(img: Image.Image, x0, x1):
    """Обрезает значок по ярким пикселям и вписывает в SIZE с сохранением пропорций. Возвращает маску 0/1."""
    a = np.asarray(img.convert("L"))[:, x0:x1] > BRIGHT
    rows = np.where(a.any(axis=1))[0]
    a = a[rows[0]:rows[-1] + 1]
    h, w = a.shape
    k = min(SIZE[0] / w, SIZE[1] / h)
    small = Image.fromarray((a * 255).astype(np.uint8)).resize((max(1, int(w * k)), max(1, int(h * k))), Image.BILINEAR)
    canvas = Image.new("L", SIZE, 0)
    canvas.paste(small, ((SIZE[0] - small.width) // 2, (SIZE[1] - small.height) // 2))
    return (np.asarray(canvas) > 127).astype(np.float32), w / h


def weapon_icon(img: Image.Image):
    """Иконка оружия — первый значок слева. Возвращает (маска, пропорция) или None."""
    blobs = split_blobs(img)
    if not blobs:
        return None
    return normalize(img, *blobs[0])


def load_templates(folder):
    """Читает эталоны: имя файла без _2, _3 — название оружия. Пропорцию восстанавливаем по закрашенной области."""
    import os
    templates = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".png"):
            continue
        mask = (np.asarray(Image.open(os.path.join(folder, f)).convert("L")) > 127).astype(np.float32)
        rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
        ratio = (cols[-1] - cols[0] + 1) / (rows[-1] - rows[0] + 1)
        name = os.path.splitext(f)[0]
        base, _, num = name.rpartition("_")
        templates.append((base if base and num.isdigit() else name, (mask, ratio)))
    return templates


MAX_MATCH = 0.5  # дальше этого от любого эталона — «неизвестно»


def classify(img: Image.Image, templates):
    """Название оружия по вырезке из ленты (или '' если иконку не нашли, '?' если не похожа ни на один эталон)."""
    icon = weapon_icon(img)
    if icon is None:
        return ""
    name, d = min(((n, distance(t, icon)) for n, t in templates), key=lambda x: x[1])
    return name if d < MAX_MATCH else "?"


def distance(a, b):
    """Насколько две иконки различаются: доля несовпавших пикселей среди закрашенных (0 — одинаковые, 1 — совсем разные)."""
    (ma, ra), (mb, rb) = a, b
    union = np.maximum(ma, mb).sum()
    if union == 0:
        return 1.0
    diff = np.abs(ma - mb).sum() / union
    return diff + 0.3 * abs(np.log(ra / rb))  # штраф за разные пропорции: пистолет не похож на винтовку
