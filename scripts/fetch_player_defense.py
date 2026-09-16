"""Official ACB 2025-26 box-score defensive counting stats, per player.

Scrapes the per-team statistics page (the same Next.js flight payload the bios
fetcher reads) and sums totals for players who appear on more than one roster.
Box-score counts only: steals, blocks, personal fouls. No tracking, no model.
"""

import concurrent.futures
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITION = 90  # acb editionId 90 == season 2025-26.
INDEX = "https://www.acb.com/es/liga/equipos/asisa-joventut-8/plantilla?editionId=90"
EXTRA = [
    "/es/liga/equipos/coviran-granada-592",
    "/es/liga/equipos/dreamland-gran-canaria-5",
]
FIELDS = (
    "numGames timePlayed starter steals blocks shotsRejected personalFouls "
    "foulsReceived turnovers rebounds defensiveRebounds offensiveRebounds"
).split()


def flight_payload(html):
    chunks = [
        json.loads(m[1])
        for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    ]
    return "".join(chunks)


def fetch(path):
    url = f"https://www.acb.com{path}/estadisticas?editionId={EDITION}"
    try:
        html = urllib.request.urlopen(url, timeout=25).read().decode()
    except Exception as e:  # noqa: BLE001 - one dead team page must not stop the run
        print(path, type(e).__name__)
        return []
    text = flight_payload(html)
    decoder = json.JSONDecoder()
    out, seen = [], set()
    for m in re.finditer(r'\{"player":\{"id":', text):
        try:
            row, _ = decoder.raw_decode(text[m.start() :])
        except ValueError:
            continue
        totals = row.get("totals")
        if not totals or "steals" not in totals:
            continue
        p = row["player"]
        key = (p["id"], totals["numGames"], totals["timePlayed"], totals["steals"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            dict(
                acbId=p["id"],
                name=p.get("nickname"),
                fullName=(p.get("firstName", "") + " " + p.get("lastName", "")).strip(),
                team=path.rsplit("/", 1)[-1],
                source=url,
                **{f: totals.get(f) for f in FIELDS},
            )
        )
    return out


def main():
    index = urllib.request.urlopen(INDEX, timeout=25).read().decode()
    paths = sorted(set(re.findall(r"/es/liga/equipos/[a-z0-9-]+", index)) | set(EXTRA))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        rows = [r for group in ex.map(fetch, paths) for r in group]
    # A player traded mid-season has one row per club; the season line is the sum.
    merged = {}
    for r in rows:
        cur = merged.get(r["acbId"])
        if cur is None:
            merged[r["acbId"]] = dict(r, team=[r["team"]], source=[r["source"]])
            continue
        cur["team"].append(r["team"])
        cur["source"].append(r["source"])
        for f in FIELDS:
            if r.get(f) is not None:
                cur[f] = (cur.get(f) or 0) + r[f]
    out = sorted(merged.values(), key=lambda r: -(r["numGames"] or 0))
    path = ROOT / "data/player_defense_acb.json"
    path.write_text(
        json.dumps(
            dict(
                edition=EDITION,
                season="2025-26",
                competition="Liga Endesa (ACB)",
                note="Official box score; regular season plus playoffs as published on acb.com.",
                players=out,
            ),
            ensure_ascii=False,
            indent=1,
        )
    )
    played = [r for r in out if (r["numGames"] or 0) > 0]
    print(
        f"Teams {len(paths)} · players {len(out)} ({len(played)} with minutes) · "
        f"steals {sum(r['steals'] or 0 for r in played)} · "
        f"blocks {sum(r['blocks'] or 0 for r in played)} · "
        f"fouls {sum(r['personalFouls'] or 0 for r in played)}"
    )


if __name__ == "__main__":
    main()
