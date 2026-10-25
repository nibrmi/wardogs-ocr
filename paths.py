"""Где лежат файлы программы и данные пользователя — одинаково для скриптов и для собранного .exe.

    resource(...)  — файлы, которые идут вместе с программой (templates/, data/attachments.json).
                     В .exe PyInstaller распаковывает их во временную папку sys._MEIPASS.
    user_dir(...)  — то, что программа пишет: сессии, статистика, настройки.
                     Из скрипта — папка проекта, из .exe — «Документы\\WARDOGS-OCR».
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)


def resource(*parts):
    return os.path.join(getattr(sys, "_MEIPASS", HERE), *parts)


def user_dir(*parts):
    base = os.path.join(os.path.expanduser("~"), "Documents", "WARDOGS-OCR") if FROZEN else HERE
    path = os.path.join(base, *parts)
    os.makedirs(path if not os.path.splitext(path)[1] else os.path.dirname(path), exist_ok=True)
    return path
