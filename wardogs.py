"""Всё в одном: трекер убийств, журнал урона, итоги матча, подсказки и сборки. Консольный запуск.
Окно с кнопками и настройками — app.py (или собранный WARDOGS-OCR.exe).

Использование:
    python wardogs.py --nick Nikita            # Ctrl+C — остановить и показать итоги
    python wardogs.py --nick Nikita --all      # печатать в терминал все убийства в ленте, а не только твои
    python wardogs.py --nick Nikita --no-shots # не сохранять снимки ленты

Один захват окна игры (Windows Graphics Capture). По строке вкладок вверху понимаем, что на экране:
  - магазин или инвентарь — подсказка предмета с цифрами; в инвентаре/обыске — ещё итог сборки оружия;
  - экран итогов («СЧЕТ») — победа/поражение и деньги за матч;
  - журнал урона (экран смерти, кнопка B) — урон, убийства, деньги;
  - обычная игра — лента убийств.
Всё пишется в sessions/<дата>*. Страница статистики по всем сессиям: python stats.py
Игру программа не трогает и ничего в неё не нажимает.
"""
import argparse
import queue
import re
import signal
import threading
import time
import tkinter as tk
from dataclasses import dataclass

import journal
from builds import Builds
from endscreen import EndScreen
from feedreader import FeedReader
from i18n import t
from live import (Session, WindowGrabber, client_rect_on_screen, find_game_window, lower_priority,
                  user32)
from feedreader import KILLFEED
from layout import to_base
from overlay import HIDE_AFTER, BuildPanels, Overlay
from shoptip import ShopTip


@dataclass
class Settings:
    nick: str = ""
    tips: bool = True          # подсказки с цифрами обвесов в магазине/инвентаре
    builds: bool = True        # итог сборки оружия в инвентаре/обыске
    killfeed: bool = True      # трекер убийств по ленте
    journal: bool = True       # журнал урона на экране смерти
    endscreen: bool = True     # итоги матча
    shots: bool = True         # сохранять снимки ленты (для разбора, ~30 МБ за 20 минут)
    tick: float = 0.4          # как часто проверять экран, секунд — главный рычаг нагрузки
    feed_interval: float = 1.5 # как часто читать ленту убийств, секунд
    print_all: bool = False
    ui_lang: str = ""          # язык программы: "ru" / "en"; пусто — по языку Windows


def worker(out: queue.Queue, stop: threading.Event, session: Session, settings: Settings, holder: dict):
    """Отдельный поток: захват и всё распознавание (OCR — в одном потоке, по очереди).
    Сообщения в очередь: {"kind": "tip"|"builds", ...}. Движки OCR создаём в этом же потоке."""
    st = ShopTip()
    reader = holder["reader"] = FeedReader(settings.nick)
    ends = EndScreen(st.engine)
    builder = Builds(st.engine)
    feed_reads, last_report = 0, time.monotonic()
    grabber, grabber_hwnd, state = None, None, None
    start, last_feed = time.monotonic(), 0.0
    while not stop.is_set():
        tick = time.monotonic()
        hwnd = find_game_window("wardogs")
        if hwnd != grabber_hwnd or (grabber and grabber.closed):  # игра запустилась, перезапустилась или закрылась
            if grabber:
                grabber.stop()
            grabber, grabber_hwnd = None, hwnd
            if hwnd:
                grabber = WindowGrabber(hwnd, region=None, finish=lambda img: img, interval_ms=300)
        new_state = (t("wait_game") if hwnd is None else t("minimized") if user32.IsIconic(hwnd) else t("working"))
        if new_state != state:
            session.note(new_state)
            state = new_state
        frame = grabber.grab() if grabber and not user32.IsIconic(hwnd) else None
        if frame is None:
            out.put({"kind": "tip", "r": None})
            out.put({"kind": "builds", "list": []})
            time.sleep(0.5 if hwnd else 1)
            continue

        x, y, w, h = client_rect_on_screen(hwnd)
        # кадр к высоте 1440 с сохранением пропорций: интерфейс игры масштабируется по высоте (см. layout.py)
        base, k = to_base(frame)
        tabs = st.tabs_text(base)     # по строке вкладок понимаем, какое меню открыто
        in_shop = st.shop_open(base, tabs)

        # 1) подсказка предмета и сборки (магазин, инвентарь, обыск)
        if in_shop and (settings.tips or settings.builds):
            tip = st.read(base, tabs)  # заодно распознаёт весь кадр — строки нужны и для сборок
            out.put({"kind": "tip", "r": tip if settings.tips else None, "wx": x, "wy": y, "k": k})
            show_builds = settings.builds and any(w in tabs.upper() for w in ("ИНВЕНТАР", "ОБЫСК", "INVENTORY", "SEARCH", "LOOT"))
            out.put({"kind": "builds", "list": builder.find(base, st.last_lines) if show_builds else [],
                     "wx": x, "wy": y, "k": k})
        else:
            out.put({"kind": "tip", "r": None})
            out.put({"kind": "builds", "list": []})

        # 2) экран итогов матча (вкладка «СЧЕТ»): копим строки, пока он открыт
        score_tab = bool("СЧЕТ" in tabs or re.search(r"\bSCORE\b", tabs.upper()))  # англ. название — предположение
        if settings.endscreen:
            done = ends.feed(base if score_tab else None)
            if done:
                session.add_match(done)

        in_menu = in_shop or score_tab
        # 3) журнал урона: открывается на экране смерти по B
        journal_now = settings.journal and not in_menu and journal.is_open(st.engine, base)
        if journal_now:
            lines = journal.read_frame(st.engine, base)
            if lines:
                session.add_journal(lines)

        # 4) лента убийств (в меню и в журнале её не видно)
        if settings.killfeed and not in_menu and not journal_now and tick - last_feed >= settings.feed_interval:
            last_feed = tick
            t = tick - start
            region = base.crop(KILLFEED)  # лента прижата к левому краю — координаты те же на любой ширине
            session.save_shot(region, t)
            session.emit(reader.read(region, t))
            feed_reads += 1
        if tick - last_report >= 300:  # раз в 5 минут — отметка в журнале сессии, чтобы было видно, что всё работает
            last_report = tick
            session.note(t("alive", n=feed_reads, k=len(session.kills)))

        time.sleep(max(0.0, settings.tick - (time.monotonic() - tick)))
    if grabber:
        grabber.stop()


class OverlayHost:
    """Окошки поверх игры (подсказка и сборки) и разбор сообщений рабочего потока. Живёт в главном потоке."""

    def __init__(self, master):
        self.tip = Overlay(master)
        self.builds = BuildPanels(master)
        self.misses = 0

    def handle(self, msg):
        if msg["kind"] == "tip":
            r = msg["r"]
            if r is None:
                self.misses += 1
                if self.misses >= HIDE_AFTER:
                    self.tip.hide()
                return
            self.misses = 0
            px, py = r["pos"]
            k = msg["k"]
            self.tip.show(r, msg["wx"] + px * k, msg["wy"] + py * k, k)
        elif msg["kind"] == "builds":
            self.builds.show(msg["list"], msg.get("wx", 0), msg.get("wy", 0), msg.get("k", 1.0))

    def hide_all(self):
        self.tip.hide()
        self.builds.hide()


class Runner:
    """Запуск и остановка всего: сессия, рабочий поток, окошки. Общий для консоли и для окна app.py."""

    def __init__(self, master, settings: Settings):
        self.master, self.settings = master, settings
        self.host = OverlayHost(master)
        self.session = Session(settings.nick, settings.print_all, shots=settings.shots)
        self.holder, self.queue, self.stop_event = {}, queue.Queue(), threading.Event()
        self.thread = threading.Thread(target=worker, args=(self.queue, self.stop_event, self.session, settings, self.holder),
                                       daemon=True)
        self.thread.start()
        self._poll()

    def _poll(self):
        if self.stop_event.is_set():
            return
        try:
            while True:
                self.host.handle(self.queue.get_nowait())
        except queue.Empty:
            pass
        self.master.after(100, self._poll)

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)
        self.host.hide_all()
        self.session.close(self.holder.get("reader"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nick", required=True)
    ap.add_argument("--all", action="store_true", help="печатать все убийства, а не только твои")
    ap.add_argument("--no-shots", action="store_true", help="не сохранять снимки ленты")
    args = ap.parse_args()

    lower_priority()
    root = tk.Tk()
    root.withdraw()
    runner = Runner(root, Settings(nick=args.nick, print_all=args.all, shots=not args.no_shots))
    # Ctrl+C в терминале: tkinter сам его не ловит, поэтому закрываем окно по сигналу
    signal.signal(signal.SIGINT, lambda *_: root.after(0, root.destroy))
    root.mainloop()
    runner.stop()


if __name__ == "__main__":
    main()
