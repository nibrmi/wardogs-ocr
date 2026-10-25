"""Подсказка с настоящими цифрами обвеса поверх магазина WARDOGS.

Использование:
    python overlay.py                       # ждёт игру; в магазине наведи мышь на обвес — рядом появятся цифры
    python overlay.py --replay <папка с кадрами> [--snap <папка>]   # проверка без игры на кадрах из видео

Как работает: раз в ~0,4 секунды берёт картинку окна игры (Windows Graphics Capture, как OBS),
проверяет, открыт ли магазин, ищет подсказку предмета (shoptip.py) и показывает рядом маленькое окно
с цифрами из data/attachments.json. Окно прозрачно для мыши — клики проходят в игру.
Игру программа не трогает и ничего в неё не нажимает. Закрыть — Ctrl+C в терминале.
"""
import argparse
import ctypes
import glob
import os
import queue
import signal
import threading
import time
import tkinter as tk

from PIL import Image, ImageGrab

from live import WindowGrabber, client_rect_on_screen, find_game_window, lower_priority, user32
from layout import to_base
from shoptip import ShopTip

BASE_H = 1440
INTERVAL = 0.4
TIP_WIDTH = 560   # примерная ширина игровой подсказки при 3440x1440 — чтобы встать справа, если слева нет места
HIDE_AFTER = 2    # столько проверок подряд без подсказки — прячем окно

# Для каких характеристик «меньше» — это хорошо (зелёный), а для каких — наоборот
LOWER_IS_BETTER = {"Вертикальная отдача", "Горизонтальная отдача", "Разброс", "Время прицеливания"}
HIGHER_IS_BETTER = {"Скорость экипировки"}
GOOD, BAD, NEUTRAL, BG, FG = "#6fdc6f", "#ff6b6b", "#c8c8c8", "#16181c", "#f0f0f0"


def colour(stat, value):
    sign = -1 if value.strip().startswith("-") else 1 if value.strip().startswith("+") else 0
    if sign == 0:
        return NEUTRAL
    if stat in LOWER_IS_BETTER:
        return GOOD if sign < 0 else BAD
    if stat in HIGHER_IS_BETTER:
        return GOOD if sign > 0 else BAD
    return NEUTRAL


def make_click_through(win):
    """Окно не перехватывает мышь и не забирает фокус у игры, не появляется на панели задач."""
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
    hwnd = user32.GetParent(win.winfo_id())
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)


class Overlay:
    def __init__(self, master):
        self.root = root = tk.Toplevel(master)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.92)
        root.configure(bg=BG)
        self.frame = tk.Frame(root, bg=BG, padx=12, pady=8, highlightthickness=1, highlightbackground="#3a3f47")
        self.frame.pack()
        root.withdraw()
        root.update_idletasks()
        make_click_through(root)
        self.shown_key = None

    def show(self, result, screen_x, screen_y, k):
        item = result["item"]
        key = item["id"] if item else result["title"]
        if key != self.shown_key:
            for w in self.frame.winfo_children():
                w.destroy()
            font = ("Segoe UI", max(9, round(11 * k)))
            bold = ("Segoe UI", max(9, round(11 * k)), "bold")
            if item:
                tk.Label(self.frame, text=item["name_ru"], font=bold, fg=FG, bg=BG, anchor="w").pack(fill="x")
                stats = item["stats"]
                if len(stats) <= 1:
                    tk.Label(self.frame, text="цифр нет — только вес", font=font, fg=NEUTRAL, bg=BG, anchor="w").pack(fill="x")
                for stat, value in stats.items():
                    row = tk.Frame(self.frame, bg=BG)
                    row.pack(fill="x")
                    tk.Label(row, text=stat, font=font, fg=NEUTRAL, bg=BG, anchor="w").pack(side="left")
                    tk.Label(row, text=value, font=bold, fg=colour(stat, value), bg=BG, anchor="e").pack(side="right", padx=(16, 0))
                if item.get("price"):
                    tk.Label(self.frame, text=f"Цена {item['price']}", font=font, fg=NEUTRAL, bg=BG, anchor="w").pack(fill="x", pady=(4, 0))
                tk.Label(self.frame, text="данные: wardogs.zone", font=("Segoe UI", max(8, round(8 * k))),
                         fg="#7d838b", bg=BG, anchor="w").pack(fill="x")
            else:
                tk.Label(self.frame, text=f"Нет в таблице:\n{result['title']}", font=font, fg=NEUTRAL, bg=BG, justify="left").pack()
            self.shown_key = key
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        x = screen_x - w - 12
        if x < 0:  # слева нет места — встаём справа от игровой подсказки
            x = screen_x + round(TIP_WIDTH * k) + 12
        self.root.geometry(f"+{int(x)}+{int(screen_y)}")
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        return int(x), int(screen_y), w, h

    def hide(self):
        self.root.withdraw()
        self.shown_key = None


class BuildPanels:
    """Окошки с итогом сборки — по одному на каждое оружие на экране (своё и, при обыске, чужое)."""

    def __init__(self, root):
        self.root = root
        self.windows = []  # [(Toplevel, frame, ключ показанного)]

    def _window(self, i):
        while len(self.windows) <= i:
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.92)
            win.configure(bg=BG)
            frame = tk.Frame(win, bg=BG, padx=12, pady=8, highlightthickness=1, highlightbackground="#3a3f47")
            frame.pack()
            win.withdraw()
            win.update_idletasks()
            make_click_through(win)
            self.windows.append([win, frame, None])
        return self.windows[i]

    def show(self, builds, wx, wy, k):
        from builds import SLOT_NAMES
        for i, b in enumerate(builds):
            slot = self._window(i)
            win, frame, shown = slot
            key = (b["weapon"], tuple(sorted((s, v["weight"]) for s, v in b["slots"].items())))
            if key != shown:
                for w in frame.winfo_children():
                    w.destroy()
                font = ("Segoe UI", max(9, round(10 * k)))
                bold = ("Segoe UI", max(9, round(11 * k)), "bold")
                tk.Label(frame, text=f"Сборка {b['weapon']} — итог", font=bold, fg=FG, bg=BG, anchor="w").pack(fill="x")
                if not b["total"]:
                    tk.Label(frame, text="модули не опознаны", font=font, fg=NEUTRAL, bg=BG, anchor="w").pack(fill="x")
                for stat, v in sorted(b["total"].items()):
                    value = f"{v:+d}%"
                    row = tk.Frame(frame, bg=BG)
                    row.pack(fill="x")
                    tk.Label(row, text=stat, font=font, fg=NEUTRAL, bg=BG, anchor="w").pack(side="left")
                    tk.Label(row, text=value, font=bold, fg=colour(stat, value), bg=BG).pack(side="right", padx=(16, 0))
                for s, v in b["slots"].items():
                    c = v["candidates"]
                    name = c[0]["name_ru"] if len(c) == 1 else (" / ".join(x["name_ru"] for x in c[:2]) + " ?") if c else "нет в таблице"
                    tk.Label(frame, text=f"{SLOT_NAMES[s]}: {name}", font=("Segoe UI", max(8, round(9 * k))),
                             fg=NEUTRAL, bg=BG, anchor="w", wraplength=round(420 * k), justify="left").pack(fill="x")
                tk.Label(frame, text="≈ эффекты перемножены; цифры — wardogs.zone", font=("Segoe UI", max(8, round(8 * k))),
                         fg="#7d838b", bg=BG, anchor="w").pack(fill="x", pady=(4, 0))
                slot[2] = key
            px, py = b["pos"]
            win.geometry(f"+{int(wx + (px + 10) * k)}+{int(wy + py * k)}")
            win.deiconify()
            win.attributes("-topmost", True)
        for win, _, _ in self.windows[len(builds):]:
            win.withdraw()
        for slot in self.windows[len(builds):]:
            slot[2] = None

    def hide(self):
        self.show([], 0, 0, 1.0)


def worker(out: queue.Queue, args, stop: threading.Event):
    """Отдельный поток: снимки и распознавание. В очередь кладёт (результат, x окна, y окна, масштаб)."""
    st = ShopTip()
    if args.replay:
        for path in sorted(glob.glob(os.path.join(args.replay, "f_*.jpg"))):
            if stop.is_set():
                return
            r = st.read(Image.open(path))
            out.put((r, 0, 0, 1.0, os.path.basename(path)))
            time.sleep(args.replay_delay)
        out.put(None)
        return

    grabber, grabber_hwnd, waiting = None, None, False
    while not stop.is_set():
        tick = time.monotonic()
        hwnd = find_game_window("wardogs")
        if hwnd != grabber_hwnd or (grabber and grabber.closed):
            if grabber:
                grabber.stop()
            grabber, grabber_hwnd = (WindowGrabber(hwnd, region=None, finish=lambda img: to_base(img)[0], interval_ms=300)
                                     if hwnd else None), hwnd
        if hwnd is None or user32.IsIconic(hwnd):
            if not waiting:
                print("Жду окно WARDOGS…")
                waiting = True
            out.put((None, 0, 0, 1.0, ""))
            time.sleep(1)
            continue
        if waiting:
            print("Игра найдена. Открой магазин и наведи мышь на обвес.")
            waiting = False
        img = grabber.grab()
        if img is not None:
            x, y, w, h = client_rect_on_screen(hwnd)
            out.put((st.read(img), x, y, h / BASE_H, ""))
        time.sleep(max(0.0, INTERVAL - (time.monotonic() - tick)))
    if grabber:
        grabber.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", help="папка с кадрами f_*.jpg 3440x1440 вместо игры")
    ap.add_argument("--replay-delay", type=float, default=0.3)
    ap.add_argument("--snap", help="для проверки: сохранять сюда скриншот окошка каждый раз, когда оно показано")
    args = ap.parse_args()

    lower_priority()
    root = tk.Tk()
    root.withdraw()
    overlay = Overlay(root)
    results, stop = queue.Queue(), threading.Event()
    threading.Thread(target=worker, args=(results, args, stop), daemon=True).start()
    misses = 0

    def poll():
        nonlocal misses
        try:
            while True:
                msg = results.get_nowait()
                if msg is None:  # повтор закончился
                    root.destroy()
                    return
                r, wx, wy, k, label = msg
                if r is None:
                    misses += 1
                    if misses >= HIDE_AFTER:
                        overlay.hide()
                    continue
                misses = 0
                px, py = r["pos"]
                box = overlay.show(r, wx + px * k, wy + py * k, k)
                name = r["item"]["name_ru"] if r["item"] else "нет в таблице"
                if label:
                    print(f"{label}: «{r['title']}» -> {name}")
                if args.snap:
                    os.makedirs(args.snap, exist_ok=True)
                    root.update()
                    time.sleep(0.05)
                    x, y, w, h = box
                    ImageGrab.grab(bbox=(x - 4, y - 4, x + w + 4, y + h + 4), all_screens=True).save(
                        os.path.join(args.snap, f"{label or int(time.time())}.png"))
        except queue.Empty:
            pass
        root.after(100, poll)

    root.after(100, poll)
    signal.signal(signal.SIGINT, lambda *_: root.after(0, root.destroy))  # Ctrl+C: tkinter сам его не ловит
    root.mainloop()
    stop.set()


if __name__ == "__main__":
    main()
