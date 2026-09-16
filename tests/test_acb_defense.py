import json
import unittest
from collections import Counter
from pathlib import Path

from epv.acb_defense import PACE_PER_40, AcbDefense
from epv.defense import fit_priors

ROOT = Path(__file__).resolve().parents[1]


class AcbDefenseTest(unittest.TestCase):
    def setUp(self):
        self.acb = AcbDefense(ROOT)

    def test_matches_nickname_against_full_legal_name(self):
        # SkillCorner carries both surnames; acb.com publishes the nickname.
        row, how = self.acb.match(0, "Usman Garuba Alari")
        self.assertEqual(row["name"], "Usman Garuba")
        self.assertEqual(how, "tokens")

    def test_refuses_an_ambiguous_token_match(self):
        # Two different Jaime Fernandez played in 2025-26; only an alias can split them.
        by_name = [r for r in self.acb.rows if r["name"] == "Jaime Fernández"]
        self.assertEqual(len(by_name), 2)
        row, _ = self.acb.match(0, "Jaime Fernandez Manzanares")
        self.assertIsNone(row)
        row, how = self.acb.match(59527, "Jaime Fernandez Manzanares")
        self.assertEqual(how, "alias")
        self.assertEqual(row["acbId"], 20212348)

    def test_possessions_scale_with_minutes_at_league_pace(self):
        row = dict(timePlayed=40 * 60)
        self.assertAlmostEqual(self.acb.possessions(row), PACE_PER_40)

    def test_pool_rate_agrees_with_the_tracking_sample(self):
        # Independent check on the minutes-to-possessions conversion: the season
        # pool should land near the 1.83/100 measured from counted possessions.
        self.assertAlmostEqual(100 * self.acb.pool_steals, 1.83, delta=0.15)

    def test_every_tracking_player_with_acb_minutes_is_matched(self):
        manifest = json.loads((ROOT / "viewer/data/manifest.json").read_text())
        names = {
            int(pid): player["name"]
            for game in manifest["games"]
            for pid, player in game["players"].items()
        }
        missing = [n for pid, n in names.items() if not self.acb.profile(pid, n)]
        # Aimar Mintegui is rostered but logged no ACB minutes in 2025-26.
        self.assertEqual(missing, ["Aimar Mintegui"])


class SeasonPriorTest(unittest.TestCase):
    def test_excluded_game_is_subtracted_from_the_season_line(self):
        counts = {1: (Counter({7: 60}), Counter({7: 3})), 2: (Counter({7: 60}), Counter({7: 1}))}
        season = {7: (20.0, 1000.0, {})}
        kept, _ = fit_priors(counts, exclude=(), season=season)
        dropped, _ = fit_priors(counts, exclude={1}, season=season)
        self.assertEqual(kept[7]["steals"], 20.0)
        self.assertEqual(kept[7]["defensivePossessions"], 1000.0)
        # Game 1 contributed 3 credited steals over 60 possessions.
        self.assertEqual(dropped[7]["steals"], 17.0)
        self.assertEqual(dropped[7]["defensivePossessions"], 940.0)
        self.assertEqual(dropped[7]["evidenceSource"], "acb-season")

    def test_players_without_a_season_line_stay_on_tracking_counts(self):
        counts = {1: (Counter({7: 60, 8: 60}), Counter({7: 3}))}
        profiles, _ = fit_priors(counts, exclude=(), season={7: (20.0, 1000.0, {})})
        self.assertEqual(profiles[8]["evidenceSource"], "tracking")
        self.assertEqual(profiles[8]["defensivePossessions"], 60.0)

    def test_season_evidence_outweighs_the_shrinkage_constant(self):
        counts = {1: (Counter({7: 60}), Counter({7: 3}))}
        tracking, _ = fit_priors(counts, exclude=())
        season, _ = fit_priors(counts, exclude=(), season={7: (20.0, 1000.0, {})})
        self.assertLess(tracking[7]["evidenceWeight"], 0.4)
        self.assertGreater(season[7]["evidenceWeight"], 0.9)


class StealPriorValidationTest(unittest.TestCase):
    """The gate in steal_risk.py runs on 39 labels; these tests do not."""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "viewer/data/steal-prior-validation.json").read_text())

    def test_season_prior_identifies_the_stealer_better_than_chance(self):
        acb = self.report["whoSteals"]["acbSeason"]
        self.assertGreater(acb["events"], 100)
        self.assertLess(acb["meanRank"], 3.0)
        self.assertGreater(acb["t"], 2.0)
        self.assertLess(acb["permutationP"], 0.05)

    def test_tracking_only_prior_carries_no_signal(self):
        # Ten games leave it anti-predictive; this is the comparison that
        # motivated replacing it, and a regression here would matter.
        tracking = self.report["whoSteals"]["trackingOnly"]
        self.assertGreater(tracking["meanRank"], self.report["whoSteals"]["acbSeason"]["meanRank"])
        self.assertLess(tracking["t"], 2.0)

    def test_steal_rate_rises_across_lineup_prior_quartiles(self):
        lineup = self.report["lineupSteals"]["acbSeason"]
        rates = [q["stealRate"] for q in lineup["quartiles"]]
        self.assertEqual(rates, sorted(rates))
        self.assertGreater(lineup["topMinusBottomPoints"], 5.0)
        self.assertGreater(lineup["z"], 2.0)


if __name__ == "__main__":
    unittest.main()
