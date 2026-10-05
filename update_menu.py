#!/usr/bin/env python3
"""Fetch Unicafe menus and write short text files for a KWGT home-screen widget.

Output (in ./menu/):
  today.txt        every Keskusta Unicafe serving lunch today
  today-vegan.txt  same, vegan dishes only (incl. vegan on request)
  favourites.txt   only the restaurants listed in FAVOURITES below
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# --- Settings you may want to change -------------------------------------
LANG = "en"            # "en" or "fi" (dish names)
SHOW_PRICES = False    # student price after each dish
SHOW_HOURS = True      # lunch hours after each restaurant name
# Restaurants for favourites.txt, matched by (part of) the name, e.g. ["Kaivopiha", "Porthania"].
FAVOURITES = []
# -------------------------------------------------------------------------

ENDPOINT = "https://unicafe.fi/wp-json/swiss/v1/restaurants"
CAMPUS = re.compile(r"keskusta|centre|center|city", re.I)
TZ = ZoneInfo("Europe/Helsinki")
OUT = Path(__file__).resolve().parent / "menu"
WEEKDAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "fi": ["Ma", "Ti", "Ke", "To", "Pe", "La", "Su"],
}
TEXT = {
    "en": {"none": "No Unicafe lunch in Keskusta today.", "next": "Next menus", "updated": "updated",
           "novegan": "No vegan dishes listed.", "nofav": "None of your favourites serve lunch today."},
    "fi": {"none": "Keskustan Unicafeissa ei lounasta tänään.", "next": "Seuraavat listat", "updated": "päivitetty",
           "novegan": "Ei vegaanisia ruokia listalla.", "nofav": "Suosikeissasi ei lounasta tänään."},
}[LANG]


def fetch():
    mock = os.environ.get("UNICAFE_MOCK")
    if mock:
        return json.loads(Path(mock).read_text(encoding="utf-8"))
    url = f"{ENDPOINT}?lang={LANG}"
    req = urllib.request.Request(url, headers={"User-Agent": "unicafe-kwgt-widget (github actions)"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            if isinstance(data, list):
                return data
            last = ValueError("unexpected response shape")
        except Exception as e:  # network hiccup, retry
            last = e
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Could not fetch Unicafe menus: {last}")


def date_key(s):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.", str(s or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _strings(x):
    """Every string inside a nested structure (dicts, lists)."""
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _strings(v)


def vegan_status(item):
    texts = [t.lower() for t in _strings({k: v for k, v in item.items() if k not in ("name", "price")})]
    texts.append(str((item.get("price") or {}).get("name") or "").lower())  # e.g. "Vegaani" line
    if any(p in t for t in texts for p in ("pyydä ve", "pyydettäessä vegaan", "on request", "ask for ve")):
        return "request"
    tokens = {w for t in texts for w in re.findall(r"[a-zäöå*]+", t)}
    if tokens & {"ve", "vegan", "vegaani", "vegaaninen", "vegansk"}:
        return "yes"
    name = str(item.get("name", "")).lower()
    if re.search(r"\bvegan|\bvegaani", name):
        return "yes"
    return "no"


def is_notice(item):
    name = ((item.get("price") or {}).get("name") or "").lower()
    return name in {"tiedoitus", "tiedotus", "notice", "announcement"}


def student_price(item):
    v = (item.get("price") or {}).get("value") or {}
    p = v.get("student") or v.get("student_hyy")
    return f"{p} €" if p and "€" not in str(p) else (p or "")


def lunch_hours(r):
    l = ((r.get("menuData") or {}).get("visitingHours") or {}).get("lounas")
    if not isinstance(l, dict):
        return ""
    for i in l.get("items") or []:
        if i and i.get("hours") and not i.get("closedException"):
            return str(i["hours"]).replace(" ", "")
    return ""


def menu_for(r, key):
    for m in (r.get("menuData") or {}).get("menus") or []:
        if date_key(m.get("date")) == key:
            return m
    return None


def block(r, menu, vegan_only):
    lines = []
    for item in menu.get("data") or []:
        if is_notice(item):
            lines.append(f"  ! {item.get('name', '').strip()}")
            continue
        vs = vegan_status(item)
        if vegan_only and vs == "no":
            continue
        mark = " 🌱" if vs == "yes" else (" (🌱)" if vs == "request" else "")
        price = f"  {student_price(item)}" if SHOW_PRICES and student_price(item) else ""
        lines.append(f"• {item.get('name', '').strip()}{mark}{price}")
    if menu.get("message"):
        lines.insert(0, f"  ! {menu['message'].strip()}")
    if not any(l.startswith("•") for l in lines):
        return None
    head = r.get("title") or (r.get("menuData") or {}).get("name") or "?"
    hrs = lunch_hours(r) if SHOW_HOURS else ""
    return "\n".join([f"{head}  {hrs}".rstrip()] + lines)


def build(restaurants, day, vegan_only=False, only=None):
    key = (day.day, day.month)
    blocks = []
    for r in sorted(restaurants, key=lambda r: str(r.get("title", ""))):
        if only is not None and not any(f.lower() in str(r.get("title", "")).lower() for f in only):
            continue
        m = menu_for(r, key)
        if m:
            b = block(r, m, vegan_only)
            if b:
                blocks.append(b)
    return blocks


def day_label(d):
    return f"{WEEKDAYS[LANG][d.weekday()]} {d.day}.{d.month}."


def main():
    data = fetch()
    centre = [r for r in data if any(CAMPUS.search(str((l or {}).get("name", ""))) for l in r.get("location") or [])]
    now = datetime.now(TZ)
    today = now.date()

    # Days that actually have dishes, so weekends can point to the next menu.
    days = sorted({(today.year, k[1], k[0]) for r in centre for m in (r.get("menuData") or {}).get("menus") or []
                   if (k := date_key(m.get("date"))) and m.get("data")})
    upcoming = [datetime(y, mo, d).date() for y, mo, d in days]
    upcoming = [d if d >= today - timedelta(days=180) else d.replace(year=d.year + 1) for d in upcoming]
    nxt = next((d for d in sorted(upcoming) if d > today), None)

    footer = f"{TEXT['updated']} {now:%H:%M}"
    variants = {
        "today.txt": dict(),
        "today-vegan.txt": dict(vegan_only=True),
        "favourites.txt": dict(only=FAVOURITES or None),
    }
    OUT.mkdir(exist_ok=True)
    for fname, kw in variants.items():
        blocks = build(centre, today, **kw)
        header = f"{day_label(today)}  Unicafe Keskusta"
        if not blocks:
            empty = TEXT["novegan"] if kw.get("vegan_only") and build(centre, today) else (
                TEXT["nofav"] if kw.get("only") and build(centre, today) else TEXT["none"])
            body = [empty]
            if nxt and not build(centre, today):
                later = build(centre, nxt, **kw)
                if later:
                    body += ["", f"{TEXT['next']}: {day_label(nxt)}", ""] + ["\n\n".join(later)]
            text = "\n".join([header, ""] + body + ["", footer])
        else:
            text = "\n\n".join([header] + blocks + [footer])
        (OUT / fname).write_text(text + "\n", encoding="utf-8")
    sample = []
    for r in centre:
        m = menu_for(r, (today.day, today.month))
        if m and m.get("data"):
            sample.append({"title": r.get("title"), "items": m["data"][:4]})
        if len(sample) == 2:
            break
    (OUT / "debug-sample.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(variants)} files for {day_label(today)} ({len(centre)} Keskusta restaurants in feed)")


if __name__ == "__main__":
    main()
