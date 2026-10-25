"""WARDOGS OCR — окно с настройками: что включить, как часто проверять экран, старт/стоп, статистика.
Из этого файла собирается WARDOGS-OCR.exe (см. build.ps1).
"""
import json
import os
import sys
import tkinter as tk
from dataclasses import asdict, fields
from tkinter import messagebox, ttk

import i18n
from i18n import t
from paths import user_dir

APP_NAME = "WARDOGS OCR"
SETTINGS_FILE = user_dir("settings.json")

TOGGLES = ["tips", "builds", "killfeed", "journal", "endscreen", "shots"]  # подписи — в i18n.py
LANGS = {"ru": "Русский", "en": "English"}


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
        return t("no_ocr", e=e)


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
        ttk.Label(top, text=t("nick")).pack(side="left")
        self.nick = tk.StringVar(value=self.settings.nick)
        ttk.Entry(top, textvariable=self.nick, width=24).pack(side="left", padx=8)
        self.lang = tk.StringVar(value=LANGS[i18n.LANG])
        lang_box = ttk.Combobox(top, textvariable=self.lang, values=list(LANGS.values()), state="readonly", width=9)
        lang_box.pack(side="right")
        lang_box.bind("<<ComboboxSelected>>", lambda _: self._lang_changed())
        ttk.Label(top, text=t("language")).pack(side="right", padx=6)

        box = ttk.LabelFrame(root, text=t("what"))
        box.pack(fill="x", **pad)
        self.vars = {}
        for key in TOGGLES:
            v = tk.BooleanVar(value=getattr(self.settings, key))
            ttk.Checkbutton(box, text=t(key), variable=v).pack(anchor="w", padx=8, pady=1)
            self.vars[key] = v

        load = ttk.LabelFrame(root, text=t("load"))
        load.pack(fill="x", **pad)
        self.tick = tk.DoubleVar(value=self.settings.tick)
        self.tick_label = ttk.Label(load)
        self.tick_label.pack(anchor="w", padx=8)
        ttk.Scale(load, from_=0.2, to=2.0, variable=self.tick, command=lambda _: self._tick_text()).pack(fill="x", padx=8)
        ttk.Label(load, text=t("tick_hint"), wraplength=520, foreground="#666").pack(anchor="w", padx=8, pady=(0, 6))
        self._tick_text()

        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.start_btn = ttk.Button(btns, text=t("start"), command=self.toggle)
        self.start_btn.pack(side="left")
        ttk.Button(btns, text=t("stats"), command=self.open_stats).pack(side="left", padx=8)
        ttk.Button(btns, text=t("data_folder"), command=lambda: os.startfile(user_dir())).pack(side="left")
        self.status = ttk.Label(btns, text=t("stopped"))
        self.status.pack(side="right")

        self.log = tk.Text(root, height=12, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, **pad)
        sys.stdout = sys.stderr = LogWriter(self.log)
        print(t("saved_to", path=user_dir()))
        print(t("credits"))
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _lang_changed(self):
        code = next(c for c, name in LANGS.items() if name == self.lang.get())
        if code != i18n.LANG:
            self.settings.ui_lang = code
            save_settings(self._collect())
            messagebox.showinfo(APP_NAME, i18n.TEXTS["restart_lang"][1 if code == "en" else 0])

    def _tick_text(self):
        self.tick_label.configure(text=t("tick", s=self.tick.get()))

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
            self.status.configure(text=t("stopping"))
            self.root.update_idletasks()
            self.runner.stop()
            self.runner = None
            self.start_btn.configure(text=t("start"))
            self.status.configure(text=t("stopped"))
            return
        s = self._collect()
        if not s.nick:
            messagebox.showwarning(APP_NAME, t("need_nick"))
            return
        from live import lower_priority
        from wardogs import Runner
        lower_priority()
        self.runner = Runner(self.root, s)
        self.start_btn.configure(text=t("stop"))
        self.status.configure(text=t("running"))

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
    i18n.set_lang(load_settings().ui_lang or i18n.default_lang())
    root = tk.Tk()
    problem = check_ocr()
    if problem:
        messagebox.showerror(APP_NAME, problem)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
