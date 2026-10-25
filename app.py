"""WARDOGS OCR — окно с настройками: что включить, как часто проверять экран, старт/стоп, статистика.
Из этого файла собирается WARDOGS-OCR.exe (см. build.ps1).
"""
import json
import os
import sys
import tkinter as tk
from dataclasses import asdict, fields
from tkinter import messagebox, ttk

from paths import user_dir

APP_NAME = "WARDOGS OCR"
SETTINGS_FILE = user_dir("settings.json")

TOGGLES = [
    ("tips", "Подсказки с цифрами обвесов (магазин, инвентарь)"),
    ("builds", "Итог сборки оружия (инвентарь, обыск; веса — клавиша F)"),
    ("killfeed", "Трекер убийств по ленте"),
    ("journal", "Журнал урона на экране смерти (кнопка B)"),
    ("endscreen", "Итоги матча (победа/поражение, деньги)"),
    ("shots", "Сохранять снимки ленты для разбора (~30 МБ за 20 минут)"),
]


def load_settings():
    from wardogs import Settings
    s = Settings()
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for fld in fields(Settings):
            if fld.name in data:
                setattr(s, fld.name, data[fld.name])
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def check_ocr():
    """Русский OCR ставится в Windows вместе с русским языковым пакетом — без него программа не работает."""
    try:
        from winocr import make_engine
        make_engine("ru")
        return None
    except Exception as e:
        return ("В Windows не найдено распознавание текста для русского языка.\n\n"
                "Как поставить: Параметры → Время и язык → Язык и регион → Добавить язык → Русский "
                "(достаточно отметить «Распознавание текста»/базовые компоненты), затем перезапустить программу.\n\n"
                f"Подробности: {e}")


class LogWriter:
    """Всё, что программа печатает (итоги, «УБИЛ/УМЕР»), — в окно журнала вместо консоли."""

    def __init__(self, text: tk.Text):
        self.text = text

    def write(self, s):
        self.text.after(0, self._append, s)

    def _append(self, s):
        self.text.configure(state="normal")
        self.text.insert("end", s)
        self.text.see("end")
        self.text.configure(state="disabled")

    def flush(self):
        pass


class App:
    def __init__(self, root):
        from wardogs import Settings  # noqa: F401 — проверка, что всё импортируется до показа окна
        self.root, self.runner = root, None
        self.settings = load_settings()
        root.title(APP_NAME)
        root.minsize(560, 520)
        pad = {"padx": 12, "pady": 4}

        top = ttk.Frame(root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Твой ник в игре:").pack(side="left")
        self.nick = tk.StringVar(value=self.settings.nick)
        ttk.Entry(top, textvariable=self.nick, width=28).pack(side="left", padx=8)

        box = ttk.LabelFrame(root, text="Что делать")
        box.pack(fill="x", **pad)
        self.vars = {}
        for key, label in TOGGLES:
            v = tk.BooleanVar(value=getattr(self.settings, key))
            ttk.Checkbutton(box, text=label, variable=v).pack(anchor="w", padx=8, pady=1)
            self.vars[key] = v

        load = ttk.LabelFrame(root, text="Нагрузка")
        load.pack(fill="x", **pad)
        self.tick = tk.DoubleVar(value=self.settings.tick)
        self.tick_label = ttk.Label(load)
        self.tick_label.pack(anchor="w", padx=8)
        ttk.Scale(load, from_=0.2, to=2.0, variable=self.tick, command=lambda _: self._tick_text()).pack(fill="x", padx=8)
        ttk.Label(load, text="Реже — меньше нагрузка на процессор, но подсказки появляются с задержкой "
                             "и короткие строки ленты могут пропасть.", wraplength=520, foreground="#666").pack(anchor="w", padx=8, pady=(0, 6))
        self._tick_text()

        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.start_btn = ttk.Button(btns, text="▶  Старт", command=self.toggle)
        self.start_btn.pack(side="left")
        ttk.Button(btns, text="Статистика", command=self.open_stats).pack(side="left", padx=8)
        ttk.Button(btns, text="Папка с данными", command=lambda: os.startfile(user_dir())).pack(side="left")
        self.status = ttk.Label(btns, text="Остановлено")
        self.status.pack(side="right")

        self.log = tk.Text(root, height=12, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, **pad)
        sys.stdout = sys.stderr = LogWriter(self.log)
        print(f"Данные сохраняются в {user_dir()}")
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _tick_text(self):
        self.tick_label.configure(text=f"Проверять экран каждые {self.tick.get():.1f} с")

    def _collect(self):
        s = self.settings
        s.nick = self.nick.get().strip()
        for key, v in self.vars.items():
            setattr(s, key, v.get())
        s.tick = round(self.tick.get(), 1)
        s.feed_interval = max(1.5, s.tick)
        save_settings(s)
        return s

    def toggle(self):
        if self.runner:
            self.status.configure(text="Останавливаю…")
            self.root.update_idletasks()
            self.runner.stop()
            self.runner = None
            self.start_btn.configure(text="▶  Старт")
            self.status.configure(text="Остановлено")
            return
        s = self._collect()
        if not s.nick:
            messagebox.showwarning(APP_NAME, "Впиши свой ник в игре — по нему трекер узнаёт твои убийства и смерти.")
            return
        from live import lower_priority
        from wardogs import Runner
        lower_priority()
        self.runner = Runner(self.root, s)
        self.start_btn.configure(text="■  Стоп")
        self.status.configure(text="Работает")

    def open_stats(self):
        import stats
        nick = self.nick.get().strip() or "?"
        path = os.path.join(stats.SESSIONS, "stats.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(stats.build(nick))
        os.startfile(path)

    def close(self):
        if self.runner:
            self.runner.stop()
        self._collect()
        self.root.destroy()


def selftest():
    """WARDOGS-OCR.exe --selftest: проверяет, что внутри сборки всё на месте. Результат — в selftest.txt."""
    report = []
    try:
        from PIL import Image, ImageDraw, ImageFont
        from winocr import make_engine, recognize
        img = Image.new("L", (600, 120), 255)
        ImageDraw.Draw(img).text((20, 30), "ПРОВЕРКА 123", fill=0, font=ImageFont.truetype("arial.ttf", 48))
        report.append("OCR: " + " ".join(l["text"] for l in recognize(make_engine("ru"), img)))
    except Exception as e:
        report.append(f"OCR: ОШИБКА {e!r}")
    for what, fn in (("захват окна", lambda: __import__("windows_capture").WindowsCapture),
                     ("таблица обвесов", lambda: f"{len(__import__('shoptip').load_items())} предметов"),
                     ("эталоны оружия", lambda: f"{len(__import__('icons').load_templates(__import__('paths').resource('templates')))} шт.")):
        try:
            report.append(f"{what}: ok {fn() if what != 'захват окна' else ''}")
        except Exception as e:
            report.append(f"{what}: ОШИБКА {e!r}")
    with open(user_dir("selftest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    root = tk.Tk()
    problem = check_ocr()
    if problem:
        messagebox.showerror(APP_NAME, problem)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
