"""Живой трекер: пока идёт матч, снимает ленту убийств с экрана и пишет убийства в файл.

Использование:
    python live.py --nick Nikita                  # ждёт окно WARDOGS и работает, Ctrl+C — стоп и итоги
    python live.py --nick Nikita --all            # печатать вообще все убийства, а не только твои
    python live.py --nick Nikita --no-shots       # не сохранять снимки ленты (по умолчанию сохраняются для разбора)
    python live.py --nick Nikita --replay <папка с кадрами> --step 5   # проверка без игры, на кадрах из видео

Как это безопасно для античита: программа не трогает процесс игры. Она находит окно по заголовку
и получает его картинку через Windows Graphics Capture — так же, как OBS «Захват окна».

Чтобы не мешать игре: картинку готовит видеокарта, программа работает с пониженным приоритетом
и читает ленту раз в полторы секунды.

Результат в sessions/:
    <дата_время>.csv        — все убийства сессии, строки дописываются сразу
    <дата_время>.log        — когда трекер работал, когда стоял на паузе
    <дата_время>_shots/     — снимки ленты (по ним можно разобрать, что пошло не так)
"""
import argparse
import csv
import ctypes
import glob
import json
import os
import time
from collections import Counter
from ctypes import wintypes
from datetime import datetime

from PIL import Image, ImageGrab

from feedreader import KILLFEED, FeedReader, format_kill

FIELDS = ["time", "clock", "killer", "victim", "weapon", "distance_m", "mine", "readings"]
BASE_W, BASE_H = 3440, 1440  # разрешение, под которое заданы координаты KILLFEED

user32 = ctypes.windll.user32
# Без этого Windows с масштабированием 125–150% отдаёт «логические» координаты, и снимок съедет.
ctypes.windll.shcore.SetProcessDpiAwareness(2)


def lower_priority():
    """Пониженный приоритет: если процессору не хватает, Windows отдаст время игре, а не нам."""
    BELOW_NORMAL_PRIORITY_CLASS = 0x4000
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)


def find_game_window(title_part):
    """Ищет окно Unreal Engine с нужным словом в заголовке. Возвращает hwnd или None."""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls, title = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        user32.GetWindowTextW(hwnd, title, 256)
        if cls.value == "UnrealWindow" and title_part.lower() in title.value.lower():
            found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def client_rect_on_screen(hwnd):
    """Рамка содержимого окна (без заголовка и рамок) в экранных координатах: x, y, ширина, высота."""
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right, rect.bottom


def scaled_killfeed(width, height):
    """Координаты ленты для окна другого размера: интерфейс игры масштабируется по высоте и прижат к левому краю."""
    k = height / BASE_H
    return tuple(round(v * k) for v in KILLFEED)


def to_base_size(img):
    size = (KILLFEED[2] - KILLFEED[0], KILLFEED[3] - KILLFEED[1])
    return img if img.size == size else img.resize(size, Image.LANCZOS)


class WindowGrabber:
    """Снимает окно игры через Windows Graphics Capture — тот же механизм, что «Захват окна» в OBS.
    Картинку готовит видеокарта и отдаёт в отдельный поток не чаще раза в полсекунды; мы храним
    только кусок с лентой. Окно снимается, даже если поверх него другое окно (но не когда свёрнуто)."""

    def __init__(self, hwnd, region=scaled_killfeed, finish=None, interval_ms=500):
        """region(ширина, высота) -> (x0, y0, x1, y1): какой кусок кадра хранить;
        finish(картинка) — что сделать с куском перед выдачей (по умолчанию — привести ленту к базовому размеру)."""
        import threading
        from windows_capture import WindowsCapture

        self.lock = threading.Lock()
        self.latest = None
        self.closed = False
        self.finish = finish or to_base_size
        cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd, minimum_update_interval=interval_ms)

        @cap.event
        def on_frame_arrived(frame, control):
            buf = frame.frame_buffer  # BGRA, весь кадр окна
            if region is None:  # весь кадр
                crop = buf[:, :, 2::-1].copy()  # BGR -> RGB
            else:
                x0, y0, x1, y1 = region(buf.shape[1], buf.shape[0])
                crop = buf[y0:y1, x0:x1, 2::-1].copy()
            with self.lock:
                self.latest = crop

        @cap.event
        def on_closed():
            self.closed = True

        self.control = cap.start_free_threaded()

    def grab(self):
        with self.lock:
            crop = self.latest
        return None if crop is None else self.finish(Image.fromarray(crop))

    def stop(self):
        try:
            self.control.stop()
        except Exception:
            pass


def grab_killfeed_gdi(hwnd):
    """Запасной способ — обычный скриншот экрана (GDI). Может давать микроподлагивания, поэтому только если WGC не завёлся."""
    x, y, w, h = client_rect_on_screen(hwnd)
    x0, y0, x1, y1 = scaled_killfeed(w, h)
    return to_base_size(ImageGrab.grab(bbox=(x + x0, y + y0, x + x1, y + y1), all_screens=True))


def summary(kills, nick):
    mine_k = [k for k in kills if k["mine"] == "убил"]
    mine_d = [k for k in kills if k["mine"] == "умер"]
    print(f"\n=== Итоги сессии ({nick}) ===")
    print(f"Убийств в ленте всего: {len(kills)}")
    print(f"Ты убил: {len(mine_k)}, умер: {len(mine_d)}"
          + (f", K/D {len(mine_k) / len(mine_d):.2f}" if mine_d else ""))
    if mine_k:
        print("Твоё оружие:", ", ".join(f"{w} — {n}" for w, n in Counter(k["weapon"] for k in mine_k).most_common()))
        dists = [k["distance_m"] for k in mine_k if k["distance_m"] != ""]
        if dists:
            print(f"Самое дальнее убийство: {max(dists)} м")
    if mine_d:
        print("Тебя убивали из:", ", ".join(f"{w} — {n}" for w, n in Counter(k["weapon"] for k in mine_d).most_common()))
        print("Чаще всех тебя убивал:", Counter(k["killer"] for k in mine_d).most_common(1)[0][0])


class Session:
    """Файлы одной игровой сессии и вывод в терминал: общее для live.py и wardogs.py."""

    def __init__(self, nick, print_all=False, shots=True):
        from paths import user_dir
        self.stem = os.path.join(user_dir("sessions"), datetime.now().strftime("%Y-%m-%d_%H-%M"))
        self.nick, self.print_all = nick, print_all
        self.out = open(self.stem + ".csv", "w", newline="", encoding="utf-8-sig")
        self.log = open(self.stem + ".log", "w", encoding="utf-8")
        self.shots_dir = self.stem + "_shots" if shots else None
        if self.shots_dir:
            os.makedirs(self.shots_dir, exist_ok=True)
        self.writer = csv.DictWriter(self.out, fieldnames=FIELDS, extrasaction="ignore")
        self.writer.writeheader()
        self.out.flush()
        self.kills = []
        print(f"Пишу в {self.stem}.csv. Ctrl+C — остановить и показать итоги.")

    def note(self, msg):
        line = f"{datetime.now():%H:%M:%S}  {msg}"
        print(line)
        self.log.write(line + "\n")
        self.log.flush()

    def save_shot(self, region, t):
        if self.shots_dir:
            region.save(os.path.join(self.shots_dir, f"{datetime.now():%H%M%S}_{int(t):05d}.jpg"), quality=80)

    def emit(self, new):
        for kill in new:
            t = kill["t"]
            kill.update(time=f"{int(t // 60)}:{int(t % 60):02d}", clock=datetime.now().strftime("%H:%M:%S"))
            self.kills.append(kill)
            self.writer.writerow(kill)
            self.out.flush()
            if kill["mine"]:
                print(f">>> {'УБИЛ' if kill['mine'] == 'убил' else 'УМЕР'}  " + format_kill(kill))
            elif self.print_all:
                print("    " + format_kill(kill))

    def add_journal(self, lines):
        """Строки журнала урона с одного кадра. Копим все кадры, склеиваем при закрытии сессии;
        сырые строки сразу пишем в файл, чтобы ничего не потерять при вылете."""
        if not hasattr(self, "journal_frames"):
            self.journal_frames = []
            self.note("Журнал урона открыт — читаю.")
        self.journal_frames.append(lines)
        with open(self.stem + "_journal_raw.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(lines, ensure_ascii=False) + "\n")

    def add_match(self, result):
        """Итоги матча с экрана «Победа/Поражение»."""
        result = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), **result}
        with open(self.stem + "_matches.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        def usd(key):
            v = result.get(key)
            return "?" if v is None else ("−" if v < 0 else "") + f"${abs(v):,}".replace(",", " ")
        self.note(f"Итоги матча: {result.get('result', '?')}, прибыль {usd('profit')}, "
                  f"заработано {usd('earned')}, потрачено {usd('spent')}")

    def close(self, reader):
        if reader:
            self.emit(reader.flush())
        self.out.close()
        self.log.close()
        summary(self.kills, self.nick)
        if getattr(self, "journal_frames", None):
            import journal
            rows = journal.drop_repeated_kills([journal.classify(t, text, self.nick)
                                                for t, text in journal.merge(self.journal_frames)])
            journal.write_csv(rows, self.stem + "_journal.csv")
            print("\n=== Журнал урона ===")
            journal.summary(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nick", required=True)
    ap.add_argument("--interval", type=float, default=1.5, help="секунд между снимками")
    ap.add_argument("--title", default="wardogs", help="часть заголовка окна игры")
    ap.add_argument("--all", action="store_true", help="печатать все убийства, а не только твои")
    ap.add_argument("--no-shots", action="store_true", help="не сохранять снимки ленты")
    ap.add_argument("--replay", help="папка с кадрами f_*.jpg вместо снимков экрана (для проверки)")
    ap.add_argument("--step", type=float, default=5.0, help="для --replay: секунд между кадрами")
    args = ap.parse_args()

    lower_priority()
    session = Session(args.nick, args.all, shots=not (args.no_shots or args.replay))
    note, emit = session.note, session.emit
    reader = FeedReader(args.nick)
    grabber, grabber_hwnd, use_gdi = None, None, False

    if args.replay:
        frames = sorted(glob.glob(os.path.join(args.replay, "f_*.jpg")))
        source = ((i * args.step, Image.open(p).crop(KILLFEED)) for i, p in enumerate(frames))
    else:
        source = None

    start, state = time.monotonic(), None
    try:
        while True:
            tick = time.monotonic()
            if source is not None:
                item = next(source, None)
                if item is None:
                    break
                t, region = item
            else:
                hwnd = find_game_window(args.title)
                if hwnd != grabber_hwnd or (grabber and grabber.closed):  # игра запустилась, перезапустилась или закрылась
                    if grabber:
                        grabber.stop()
                    grabber, grabber_hwnd = None, hwnd
                    if hwnd and not use_gdi:
                        try:
                            grabber = WindowGrabber(hwnd)
                        except Exception as e:
                            note(f"Windows Graphics Capture не завёлся ({e}) — перехожу на обычные скриншоты.")
                            use_gdi = True
                if hwnd is None:
                    new_state = "Жду окно WARDOGS…"
                elif use_gdi and user32.GetForegroundWindow() != hwnd:
                    new_state = "Окно игры не активно — пауза (снимки не делаются)."
                elif user32.IsIconic(hwnd):
                    new_state = "Игра свёрнута — пауза."
                else:
                    new_state = "Слежу за лентой" + (" (обычные скриншоты)." if use_gdi else " (захват окна).")
                if new_state != state:
                    note(new_state)
                    state = new_state
                if not new_state.startswith("Слежу"):
                    time.sleep(1)
                    continue
                t = tick - start
                region = grab_killfeed_gdi(hwnd) if use_gdi else grabber.grab()
                if region is None:  # первый кадр ещё не пришёл
                    time.sleep(0.2)
                    continue
                session.save_shot(region, t)

            emit(reader.read(region, t))

            if source is None:
                time.sleep(max(0.0, args.interval - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        pass
    finally:
        if grabber:
            grabber.stop()
        session.close(reader)


if __name__ == "__main__":
    main()
