"""Join official ACB box-score defensive counts onto tracking player ids.

Source: data/player_defense_acb.json (scripts/fetch_player_defense.py), the
acb.com per-team statistics pages for editionId 90 == season 2025-26.

The box score counts steals per *game*, not per defensive possession, so
exposure is estimated from minutes at the league pace measured in our own
tracking games. That estimate is the only modelled step here; the counts
themselves are official.
"""

import csv
import json
import unicodedata
from collections import defaultdict

# Defensive possessions faced by one team per 40 minutes, measured from the
# tracking sample (1564 possessions over 10 games, both teams).
PACE_PER_40 = 78.2


def normalized(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value or "").lower()
        if c.isalnum() and not unicodedata.combining(c)
    )


def tokens(value):
    parts = unicodedata.normalize("NFKD", value or "").lower().split()
    out = set()
    for part in parts:
        clean = "".join(c for c in part if c.isalnum() and not unicodedata.combining(c))
        # Generational suffixes are inconsistent between the two feeds.
        if clean and clean not in {"jr", "ii", "iii", "iv"}:
            out.add(clean)
    return out


class AcbDefense:
    def __init__(self, root):
        payload = json.loads((root / "data/player_defense_acb.json").read_text())
        self.season = payload["season"]
        self.rows = [r for r in payload["players"] if (r.get("numGames") or 0) > 0]
        self.by_acb = {r["acbId"]: r for r in self.rows}
        self.by_name = {}
        for r in self.rows:
            for key in ("name", "fullName"):
                self.by_name.setdefault(normalized(r[key]), r)
        self.by_token = defaultdict(list)
        for r in self.rows:
            for key in ("name", "fullName"):
                for token in tokens(r[key]):
                    self.by_token[token].append(r)
        with (root / "data/player_id_aliases.csv").open() as handle:
            aliases = list(csv.DictReader(handle))
        self.acb_of = {
            int(a["canonical_player_id"]): int(a["acb_player_id"]) for a in aliases
        }
        self.canonical = {
            int(a["player_id"]): int(a["canonical_player_id"]) for a in aliases
        }
        total_possessions = sum(self.possessions(r) for r in self.rows)
        self.pool_steals = sum(r["steals"] for r in self.rows) / total_possessions
        self.pool_blocks = sum(r["blocks"] for r in self.rows) / total_possessions
        self.pool_fouls = sum(r["personalFouls"] for r in self.rows) / total_possessions

    @staticmethod
    def possessions(row):
        return (row["timePlayed"] or 0) / 60 / 40 * PACE_PER_40

    def match(self, player_id, name):
        """Alias id first, then exact name, then a unique two-token overlap."""
        canonical = self.canonical.get(player_id, player_id)
        row = self.by_acb.get(self.acb_of.get(canonical))
        if row:
            return row, "alias"
        row = self.by_name.get(normalized(name))
        if row:
            return row, "name"
        wanted = tokens(name)
        if len(wanted) < 2:
            return None, None
        scored = defaultdict(int)
        for token in wanted:
            for candidate in self.by_token.get(token, ()):
                scored[candidate["acbId"]] += 1
        # Two shared name parts, and no runner-up at the same depth.
        best = sorted(scored.items(), key=lambda kv: -kv[1])
        if best and best[0][1] >= 2 and (len(best) == 1 or best[1][1] < best[0][1]):
            return self.by_acb[best[0][0]], "tokens"
        return None, None

    def profile(self, player_id, name):
        row, how = self.match(player_id, name)
        if not row:
            return None
        possessions = self.possessions(row)
        return dict(
            acbId=row["acbId"],
            acbName=row["name"],
            match=how,
            season=self.season,
            games=row["numGames"],
            minutes=round((row["timePlayed"] or 0) / 60, 1),
            possessions=round(possessions, 1),
            steals=row["steals"],
            blocks=row["blocks"],
            personalFouls=row["personalFouls"],
            foulsReceived=row["foulsReceived"],
            stealsPer100=round(100 * row["steals"] / possessions, 3),
            blocksPer100=round(100 * row["blocks"] / possessions, 3),
            foulsPer100=round(100 * row["personalFouls"] / possessions, 3),
        )
