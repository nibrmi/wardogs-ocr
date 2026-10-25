"""Тонкая обёртка над встроенным OCR Windows (Windows.Media.Ocr).

Берёт картинку PIL, отдаёт список строк: текст и прямоугольник каждой строки.
"""
import asyncio
import io

from PIL import Image
from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream


def make_engine(lang="ru"):
    engine = OcrEngine.try_create_from_language(Language(lang))
    if engine is None:
        raise RuntimeError(f"В Windows не установлен OCR для языка {lang}")
    return engine


async def _recognize(engine, img: Image.Image):
    # Windows OCR принимает SoftwareBitmap: кладём PNG в поток в памяти и декодируем его.
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(buf.getvalue())
    await writer.store_async()
    stream.seek(0)
    bitmap = await (await BitmapDecoder.create_async(stream)).get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)

    lines = []
    for line in result.lines:
        words = list(line.words)
        x0 = min(w.bounding_rect.x for w in words)
        y0 = min(w.bounding_rect.y for w in words)
        x1 = max(w.bounding_rect.x + w.bounding_rect.width for w in words)
        y1 = max(w.bounding_rect.y + w.bounding_rect.height for w in words)
        lines.append({
            "text": line.text,
            "box": (x0, y0, x1, y1),
            "words": [(w.text, w.bounding_rect.x, w.bounding_rect.x + w.bounding_rect.width) for w in words],
        })
    return lines


def recognize(engine, img: Image.Image):
    return asyncio.run(_recognize(engine, img))
