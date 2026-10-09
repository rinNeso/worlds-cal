#!/usr/bin/env python3
"""Build an iCalendar feed of the current League of Legends Worlds.

Pulls the schedule from the API behind lolesports.com and writes
public/worlds.ics. Stdlib only, so the workflow needs no installs.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://esports-api.lolesports.com/persisted/gw"
# Public key that lolesports.com ships in its own frontend bundle.
API_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
LEAGUE_ID = "98767975604431411"  # Worlds
WATCH_URL = "https://lolesports.com/live/worlds"
OUT = Path(__file__).parent / "public" / "worlds.ics"

# Calendar block length by series length. A Swiss day spaces Bo3s three
# hours apart, so that's the realistic slot.
SLOT_HOURS = {1: 1, 3: 3, 5: 4.5}


def get(endpoint, **params):
    params["hl"] = "en-US"
    url = f"{API}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"x-api-key": API_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]


def current_tournament():
    # Newest first, so the head of the list is this year's Worlds.
    return get("getTournamentsForLeague", leagueId=LEAGUE_ID)["leagues"][0]["tournaments"][0]


def all_events():
    """Walk the schedule's pages in both directions from the default page."""
    first = get("getSchedule", leagueId=LEAGUE_ID)["schedule"]
    events = list(first["events"])
    for direction in ("older", "newer"):
        token = first["pages"][direction]
        while token:
            page = get("getSchedule", leagueId=LEAGUE_ID, pageToken=token)["schedule"]
            events.extend(page["events"])
            token = page["pages"][direction]
            # Older pages run back years; stop once past anything we want.
            if direction == "older" and page["events"] and page["events"][0]["startTime"] < "2020":
                break
    return events


def esc(text):
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    """RFC 5545 line folding: 75 octets max, continuation lines start with a space."""
    raw = line.encode()
    out = []
    while len(raw) > 75:
        cut = 75 if not out else 74
        while cut and (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode())
        raw = raw[cut:]
    out.append(raw.decode())
    return "\r\n ".join(out)


def ics_time(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def vevent(e, stamp):
    m = e["match"]
    a, b = m["teams"]
    best_of = m["strategy"]["count"]
    stage = e.get("blockName") or "Worlds"
    start = datetime.fromisoformat(e["startTime"].replace("Z", "+00:00"))
    end = start + timedelta(hours=SLOT_HOURS.get(best_of, best_of))

    if e["state"] == "completed":
        title = f"{a['code']} {a['result']['gameWins']}–{b['result']['gameWins']} {b['code']}"
    else:
        title = f"{a['code']} vs {b['code']}"
    summary = f"{title} · {stage}"

    lines = [f"{stage}, best of {best_of}"]
    for t in (a, b):
        if t["code"] != "TBD":
            rec = t.get("record")
            rec = f" ({rec['wins']}-{rec['losses']})" if rec else ""
            lines.append(f"{t['name']}{rec}")
    lines.append(f"Watch: {WATCH_URL}")

    return [
        "BEGIN:VEVENT",
        f"UID:lolesports-{m['id']}@worlds-cal",
        f"DTSTAMP:{stamp}",
        f"LAST-MODIFIED:{stamp}",
        f"DTSTART:{ics_time(start)}",
        f"DTEND:{ics_time(end)}",
        f"SUMMARY:{esc(summary)}",
        f"DESCRIPTION:{esc(chr(10).join(lines))}",
        f"URL:{WATCH_URL}",
        "TRANSP:TRANSPARENT",  # don't mark you busy
        "END:VEVENT",
    ]


def main():
    t = current_tournament()
    lo, hi = t["startDate"], (datetime.fromisoformat(t["endDate"]) + timedelta(days=1)).date().isoformat()
    matches = {}
    for e in all_events():
        if e.get("type") == "match" and lo <= e["startTime"][:10] <= hi:
            matches[e["match"]["id"]] = e  # pages can overlap; dedupe by id
    if not matches:
        sys.exit(f"no matches found for {t['slug']} ({lo}..{hi}); refusing to publish an empty feed")

    stamp = ics_time(datetime.now(timezone.utc))
    name = t["slug"].replace("worlds_", "Worlds ")
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//rinNeso//worlds-cal//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc('LoL ' + name)}",
        "X-WR-CALDESC:League of Legends World Championship matches. Updates as teams are decided.",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for e in sorted(matches.values(), key=lambda e: e["startTime"]):
        out += vevent(e, stamp)
    out.append("END:VCALENDAR")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("".join(fold(l) + "\r\n" for l in out), encoding="utf-8", newline="")
    print(f"{t['slug']}: wrote {len(matches)} matches to {OUT}")


if __name__ == "__main__":
    main()
