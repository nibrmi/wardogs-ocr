"""Страница статистики по всем сессиям: sessions/stats.html (открывается в браузере, всё локально).

Использование:
    python stats.py --nick Nikita

Берёт из sessions/:
    <дата>.csv              — лента убийств (кто кого, из чего, с какой дистанции)
    <дата>_journal.csv      — журнал урона (урон, попадания, деньги)
    <дата>_matches.jsonl    — итоги матчей (победа/поражение, деньги)
OCR читает ники по-разному («sQUICK'» / «s0UlCk'»), поэтому похожие ники склеиваются в один.
"""
import argparse
import csv
import glob
import html
import json
import os
import statistics
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from paths import user_dir
from shoptip import loose

SESSIONS = user_dir("sessions")


# ---------- данные ----------

def load():
    feed, journal, matches, sessions = [], [], [], []
    for path in sorted(glob.glob(os.path.join(SESSIONS, "*.csv"))):
        name = os.path.basename(path)
        if name.endswith(".old.csv") or "_journal" in name:
            continue
        stem = path[:-4]
        sid = os.path.basename(stem)
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        for r in rows:
            r["session"] = sid
        feed += rows
        jpath = stem + "_journal.csv"
        jrows = list(csv.DictReader(open(jpath, encoding="utf-8-sig"))) if os.path.exists(jpath) else []
        for r in jrows:
            r["session"] = sid
        journal += jrows
        mpath = stem + "_matches.jsonl"
        if os.path.exists(mpath):
            for line in open(mpath, encoding="utf-8"):
                if line.strip():
                    matches.append({**json.loads(line), "session": sid})
        sessions.append(sid)
    return feed, journal, matches, sessions


class Names:
    """Склейка вариантов одного ника: ключ без регистра и похожих букв + нечёткое сравнение."""

    def __init__(self, names, threshold=0.82):
        counts = Counter(n for n in names if n)
        self.canon = {}
        groups = []  # [ключ, Counter вариантов]
        for name, _ in counts.most_common():
            key = loose(name)
            g = next((g for g in groups if key and (key == g[0] or SequenceMatcher(None, key, g[0]).ratio() >= threshold)), None)
            if g is None:
                g = [key, Counter()]
                groups.append(g)
            g[1][name] += counts[name]
        for _, variants in groups:
            best = max(variants, key=lambda v: (variants[v], sum(c.isascii() for c in v)))
            for v in variants:
                self.canon[v] = best

    def __call__(self, name):
        return self.canon.get(name, name)


def num(x):
    try:
        return float(str(x).replace(",", "."))
    except ValueError:
        return None


# ---------- HTML ----------

def esc(x):
    return html.escape(str(x))


def money(x):
    return ("−" if x < 0 else "") + f"${abs(x):,.0f}".replace(",", " ")


def bar_table(title, rows, value_label, fmt=lambda v: f"{v:,.0f}".replace(",", " "), extra_head=(), note=""):
    """rows: [(подпись, значение, [доп. колонки...])]. Полоска — длина значения относительно максимума."""
    if not rows:
        return f'<section><h2>{esc(title)}</h2><p class="muted">Пока нет данных.</p></section>'
    top = max(v for _, v, *_ in rows) or 1
    head = "".join(f"<th>{esc(h)}</th>" for h in extra_head)
    body = []
    for label, value, *extra in rows:
        cells = "".join(f'<td class="num">{esc(c)}</td>' for c in (extra[0] if extra else []))
        pct = max(1.5, 75 * value / top)  # максимум 75% ширины — чтобы число справа от полоски всегда помещалось
        body.append(f'<tr><td class="label">{esc(label)}</td>'
                    f'<td class="barcell" title="{esc(label)}: {esc(fmt(value))} {esc(value_label)}">'
                    f'<div class="bar" style="width:{pct:.1f}%"></div><span>{esc(fmt(value))}</span></td>{cells}</tr>')
    note_html = f'<p class="muted">{esc(note)}</p>' if note else ""
    return (f'<section><h2>{esc(title)}</h2>{note_html}<table><thead><tr><th></th><th>{esc(value_label)}</th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></section>')


def tiles(items):
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="tv">{esc(v)}</div><div class="tl">{esc(l)}</div></div>' for l, v in items) + "</div>"


CSS = """
:root{--bg:#f6f6f4;--card:#fff;--ink:#1d1f22;--ink2:#55595f;--muted:#8a8f96;--line:#e3e3df;--bar:#3a7bd5;--bartrack:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#141619;--card:#1c1f23;--ink:#ecedee;--ink2:#b3b7bd;--muted:#80858c;--line:#2c3036;--bar:#5b9bf0;--bartrack:#252a31}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 "Segoe UI",system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 4px}h2{font-size:17px;margin:0 0 10px}
.muted{color:var(--muted);font-size:13px;margin:4px 0 10px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0 24px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.tv{font-size:24px;font-weight:600}.tl{color:var(--ink2);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:16px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;color:var(--muted);font-weight:500;font-size:12px;padding:4px 6px;border-bottom:1px solid var(--line)}
td{padding:4px 6px;border-bottom:1px solid var(--line);vertical-align:middle}tr:last-child td{border-bottom:0}
td.label{white-space:nowrap;max-width:260px;overflow:hidden;text-overflow:ellipsis}td.num{text-align:right;white-space:nowrap;color:var(--ink2)}
td.barcell{position:relative;min-width:180px;width:45%;white-space:nowrap}td.barcell .bar{height:14px;background:var(--bar);border-radius:0 4px 4px 0;display:inline-block;vertical-align:middle}
td.barcell span{margin-left:8px;color:var(--ink);font-variant-numeric:tabular-nums}
tr:hover td{background:var(--bartrack)}
@media (max-width:560px){.grid{grid-template-columns:1fr}td.barcell{min-width:120px}}
"""


def build(nick):
    feed, journal, matches, sessions = load()
    names = Names([r.get("killer", "") for r in feed] + [r.get("victim", "") for r in feed]
                  + [r.get("who", "") for r in journal] + [r.get("whom", "") for r in journal])
    for r in feed:
        r["killer"], r["victim"] = names(r.get("killer", "")), names(r.get("victim", ""))
    for r in journal:
        r["who"], r["whom"] = names(r.get("who", "")), names(r.get("whom", ""))
    # оружие: в ленте названия из templates/ (латиница «AK-74»), в журнале — из игры (кириллица «АК-74»)
    weapons = Names([r.get("weapon", "") for r in feed + journal], threshold=0.95)
    for r in feed + journal:
        if r.get("weapon"):
            r["weapon"] = weapons(r["weapon"])

    my_kills = [r for r in feed if r.get("mine") == "убил"]
    my_deaths = [r for r in feed if r.get("mine") == "умер"]
    others = [r for r in feed if not r.get("mine")]

    # --- общая сводка
    wins = sum(1 for m in matches if m.get("result") == "победа")
    profit = sum(m.get("profit", 0) for m in matches)
    kd = f"{len(my_kills) / len(my_deaths):.2f}" if my_deaths else "—"
    dists = [num(r["distance_m"]) for r in my_kills if num(r.get("distance_m"))]
    out = [f"<h1>WARDOGS — статистика {esc(nick)}</h1>",
           f'<p class="muted">Сессий: {len(sessions)} · данные из ленты убийств, журнала урона и экранов итогов · '
           f'ники склеены с учётом ошибок распознавания</p>']
    out.append(tiles([
        ("Матчей с итогами", f"{len(matches)} ({wins} побед)" if matches else "—"),
        ("Прибыль за матчи", money(profit) if matches else "—"),
        ("Убийств", len(my_kills)), ("Смертей", len(my_deaths)), ("K/D", kd),
        ("Самое дальнее убийство", f"{max(dists):.0f} м" if dists else "—"),
    ]))

    sections = []

    # --- деньги
    money_rows = [r for r in journal if r.get("type") == "деньги" and num(r.get("value"))]
    if money_rows:
        # только почти одинаковые тексты — «Присутствие в Hot Zone» и «…в Control Zone» разные начисления
        reasons = Names([r["what"] for r in money_rows], threshold=0.93)
        total, count = defaultdict(float), Counter()
        for r in money_rows:
            k = reasons(r["what"])
            total[k] += num(r["value"])
            count[k] += 1
        rows = [(k, v, [f"×{count[k]}"]) for k, v in sorted(total.items(), key=lambda kv: -kv[1])]
        sections.append(bar_table("На чём зарабатываешь", rows, "$", fmt=money, extra_head=("раз",),
                                  note="Из журнала урона. Видна только та часть журнала, что была на экране, когда ты его открывал."))
    if matches:
        rows = [(f"{m.get('time', m['session'])} — {m.get('result', '?')}", m.get("profit", 0),
                 [money(m.get("earned", 0)), money(m.get("spent", 0))]) for m in matches]
        sections.append(bar_table("Матчи", rows, "прибыль", fmt=money, extra_head=("заработано", "потрачено")))

    # --- твоё оружие
    by_w = defaultdict(lambda: [0, 0.0, 0])  # попадания, урон, убийства
    for r in journal:
        if r.get("type") == "урон нанесён":
            w = by_w[r.get("weapon") or "?"]
            w[0] += 1
            w[1] += num(r.get("value")) or 0
    for r in my_kills:
        by_w[r.get("weapon") or "?"][2] += 1
    rows = [(w, v[2], [v[0], f"{v[1]:.0f}"]) for w, v in sorted(by_w.items(), key=lambda kv: (-kv[1][2], -kv[1][0])) if w != "?"]
    sections.append(bar_table("Твоё оружие", rows, "убийств", extra_head=("попаданий", "урон"),
                              note="Убийства — из ленты, попадания и урон — из журнала урона."))

    parts = Counter(r.get("part") for r in journal if r.get("type") == "урон нанесён" and r.get("part"))
    sections.append(bar_table("Куда ты попадаешь", parts.most_common(), "попаданий"))

    # --- враги
    sections.append(bar_table("Кто чаще всех убивает тебя", [(k, n, [Counter(r["weapon"] for r in my_deaths if r["killer"] == k).most_common(1)[0][0]])
                                                            for k, n in Counter(r["killer"] for r in my_deaths).most_common(10)],
                              "раз", extra_head=("чем",)))
    sections.append(bar_table("Кого чаще всех убиваешь ты", Counter(r["victim"] for r in my_kills).most_common(10), "раз"))
    sections.append(bar_table("Из чего тебя убивают", Counter(r["weapon"] or "?" for r in my_deaths).most_common(), "раз"))

    # --- другие игроки
    pk, pd, pw = Counter(), Counter(), defaultdict(Counter)
    for r in feed:
        if r["killer"]:
            pk[r["killer"]] += 1
            if r.get("weapon") and r["weapon"] != "?":
                pw[r["killer"]][r["weapon"]] += 1
        if r["victim"]:
            pd[r["victim"]] += 1
    rows = [(p, n, [pd[p], f"{n / pd[p]:.1f}" if pd[p] else "—", pw[p].most_common(1)[0][0] if pw[p] else "?"])
            for p, n in pk.most_common(20) if p != nick]
    sections.append(bar_table("Лучшие игроки по убийствам", rows, "убийств", extra_head=("смертей", "K/D", "любимое оружие")))

    # --- мета оружия
    wk = Counter(r["weapon"] for r in feed if r.get("weapon") and r["weapon"] != "?")
    wdist = defaultdict(list)
    for r in feed:
        d = num(r.get("distance_m"))
        if d and r.get("weapon"):
            wdist[r["weapon"]].append(d)
    rows = [(w, n, [f"{statistics.median(wdist[w]):.0f} м" if wdist[w] else "—"]) for w, n in wk.most_common(20)]
    sections.append(bar_table("Мета: каким оружием убивают чаще всего", rows, "убийств", extra_head=("медиана дистанции",),
                              note="По всем убийствам в ленте. Дистанция видна только в строках с тобой."))

    # --- по сессиям
    per = []
    for sid in sessions:
        k = sum(1 for r in my_kills if r["session"] == sid)
        d = sum(1 for r in my_deaths if r["session"] == sid)
        per.append((sid, sum(1 for r in feed if r["session"] == sid), [k, d, f"{k / d:.2f}" if d else "—"]))
    sections.append(bar_table("Сессии", per, "убийств в ленте", extra_head=("убил", "умер", "K/D")))

    out.append('<div class="grid">' + "".join(sections) + "</div>")
    return ("<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>WARDOGS статистика</title><style>{CSS}</style></head><body><main>{''.join(out)}</main></body></html>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nick", required=True)
    ap.add_argument("--no-open", action="store_true", help="не открывать страницу в браузере")
    args = ap.parse_args()
    path = os.path.join(SESSIONS, "stats.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build(args.nick))
    print(f"Готово: {os.path.abspath(path)}")
    if not args.no_open:
        os.startfile(os.path.abspath(path))


if __name__ == "__main__":
    main()
