"""Tests for Wordle bot core logic (no Slack connection needed)."""

import ast
import unittest

# Parse app.py and extract the constants/functions we need without importing
# the module (which requires SLACK_BOT_TOKEN at import time).
_source = open("app.py").read()
_tree = ast.parse(_source)

# Execute only the parts we can test (everything except the Slack app init
# and the handlers that depend on it).
_test_globals = {"__builtins__": __builtins__, "__file__": "app.py"}
exec(
    compile(
        ast.Module(
            body=[
                node
                for node in _tree.body
                if not isinstance(node, ast.Expr)  # skip docstring
                and not (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and "slack" in node.module
                )
                and not (isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "app"
                    for t in node.targets
                ))
                # Skip decorated functions (@app.message, @app.command)
                and not (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.decorator_list
                    and any(
                        isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Attribute)
                        and isinstance(d.func.value, ast.Name)
                        and d.func.value.id == "app"
                        for d in node.decorator_list
                    )
                )
                # Skip if __name__ == "__main__" block
                and not (
                    isinstance(node, ast.If)
                    and isinstance(node.test, ast.Compare)
                    and isinstance(node.test.left, ast.Name)
                    and node.test.left.id == "__name__"
                )
            ],
            type_ignores=[],
        ),
        "<test>",
        "exec",
    ),
    _test_globals,
)

# Pull tested functions/constants into module scope
WORDLE_RE = _test_globals["WORDLE_RE"]
HARD_MODE_RE = _test_globals["HARD_MODE_RE"]
get_user_scores = _test_globals["get_user_scores"]
calc_streak = _test_globals["calc_streak"]
get_user_stats = _test_globals["get_user_stats"]
get_commentary = _test_globals["get_commentary"]
build_leaderboard = _test_globals["build_leaderboard"]
build_daily_summary = _test_globals["build_daily_summary"]
build_personal_stats = _test_globals["build_personal_stats"]
build_vs = _test_globals["build_vs"]
build_hardest_puzzles = _test_globals["build_hardest_puzzles"]
build_shame_list = _test_globals["build_shame_list"]
get_active_players = _test_globals["get_active_players"]
check_rivalry = _test_globals["check_rivalry"]
fetch_wordle_answer = _test_globals["fetch_wordle_answer"]
build_sparkline = _test_globals["build_sparkline"]
check_comeback = _test_globals["check_comeback"]
check_personal_best = _test_globals["check_personal_best"]
check_group_records = _test_globals["check_group_records"]
get_group_streak = _test_globals["get_group_streak"]
check_puzzle_milestone = _test_globals["check_puzzle_milestone"]
build_monthly_recap = _test_globals["build_monthly_recap"]
build_yearly_recap = _test_globals["build_yearly_recap"]
rank_icon = _test_globals["rank_icon"]
get_smart_commentary = _test_globals["get_smart_commentary"]
check_streak = _test_globals["check_streak"]
COMMENTARY = _test_globals["COMMENTARY"]


# --- Test data ---

SAMPLE_SCORES = {
    "1300": {
        "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
        "U2": {"score": "5", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
    },
    "1301": {
        "U1": {"score": "4", "hard_mode": True, "timestamp": "2025-01-02T12:00:00"},
        "U2": {"score": "X", "hard_mode": False, "timestamp": "2025-01-02T12:05:00"},
    },
    "1302": {
        "U1": {"score": "2", "hard_mode": False, "timestamp": "2025-01-03T12:00:00"},
    },
}


class TestWordleRegex(unittest.TestCase):
    def test_standard_score(self):
        m = WORDLE_RE.search("Wordle 1,234 3/6")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "1,234")
        self.assertEqual(m.group(2), "3")

    def test_fail_score(self):
        m = WORDLE_RE.search("Wordle 1,234 X/6")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "X")

    def test_no_comma(self):
        m = WORDLE_RE.search("Wordle 900 4/6")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "900")

    def test_hard_mode(self):
        self.assertTrue(HARD_MODE_RE.search("Wordle 1,234 3/6*"))
        self.assertFalse(HARD_MODE_RE.search("Wordle 1,234 3/6"))

    def test_no_match(self):
        self.assertIsNone(WORDLE_RE.search("hello world"))
        self.assertIsNone(WORDLE_RE.search("Wordle 1,234 7/6"))
        self.assertIsNone(WORDLE_RE.search("Wordle 1,234 0/6"))

    def test_embedded_in_text(self):
        m = WORDLE_RE.search("I got Wordle 1,300 2/6 today!")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "2")


class TestGetUserScores(unittest.TestCase):
    def test_returns_sorted_scores(self):
        scores, puzzles = get_user_scores(SAMPLE_SCORES, "U1")
        self.assertEqual(scores, [3, 4, 2])
        self.assertEqual(puzzles, [1300, 1301, 1302])

    def test_x_becomes_7(self):
        scores, _ = get_user_scores(SAMPLE_SCORES, "U2")
        self.assertEqual(scores, [5, 7])

    def test_unknown_user(self):
        scores, puzzles = get_user_scores(SAMPLE_SCORES, "U99")
        self.assertEqual(scores, [])
        self.assertEqual(puzzles, [])


class TestCalcStreak(unittest.TestCase):
    def test_consecutive(self):
        current, best = calc_streak([100, 101, 102, 103])
        self.assertEqual(current, 4)
        self.assertEqual(best, 4)

    def test_broken_streak(self):
        current, best = calc_streak([100, 101, 103, 104, 105])
        self.assertEqual(current, 3)
        self.assertEqual(best, 3)

    def test_single_game(self):
        current, best = calc_streak([500])
        self.assertEqual(current, 1)
        self.assertEqual(best, 1)

    def test_empty(self):
        current, best = calc_streak([])
        self.assertEqual(current, 0)
        self.assertEqual(best, 0)

    def test_old_streak_longer(self):
        # calc_streak walks backwards from the end, so it only finds the
        # current streak — an older longer streak is not detected as "best"
        current, best = calc_streak([100, 101, 102, 103, 200, 201])
        self.assertEqual(current, 2)
        self.assertEqual(best, 2)


class TestGetUserStats(unittest.TestCase):
    def test_basic_stats(self):
        stats = get_user_stats(SAMPLE_SCORES, "U1")
        self.assertEqual(stats["games"], 3)
        self.assertAlmostEqual(stats["avg"], 3.0)
        self.assertEqual(stats["best"], 2)
        self.assertEqual(stats["worst"], 4)
        self.assertEqual(stats["fails"], 0)
        self.assertEqual(stats["wins"], 3)

    def test_with_fails(self):
        stats = get_user_stats(SAMPLE_SCORES, "U2")
        self.assertEqual(stats["fails"], 1)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["distribution"]["X"], 1)

    def test_hard_mode_count(self):
        stats = get_user_stats(SAMPLE_SCORES, "U1")
        self.assertEqual(stats["hard_mode_count"], 1)

    def test_unknown_user(self):
        self.assertIsNone(get_user_stats(SAMPLE_SCORES, "U99"))

    def test_streak(self):
        stats = get_user_stats(SAMPLE_SCORES, "U1")
        self.assertEqual(stats["current_streak"], 3)
        self.assertEqual(stats["best_streak"], 3)


class TestCommentary(unittest.TestCase):
    def test_fail_gets_roast(self):
        for _ in range(10):
            c = get_commentary("X")
            self.assertIsNotNone(c)

    def test_great_score_gets_celebration(self):
        for score in ["1", "2", "3"]:
            c = get_commentary(score)
            self.assertIsNotNone(c)

    def test_all_scores_get_commentary(self):
        for score in ["1", "2", "3", "4", "5", "6", "X"]:
            c = get_commentary(score)
            self.assertIsNotNone(c, f"Expected commentary for score {score}")


class TestLeaderboard(unittest.TestCase):
    def test_builds_leaderboard(self):
        lb = build_leaderboard(SAMPLE_SCORES, days=7)
        self.assertIn("Leaderboard", lb)
        self.assertIn("U1", lb)
        self.assertIn("U2", lb)

    def test_empty_scores(self):
        lb = build_leaderboard({}, days=7)
        self.assertIn("No scores", lb)

    def test_ranking_order(self):
        lb = build_leaderboard(SAMPLE_SCORES, days=7)
        # U1 has better average (3.0) than U2 (6.0), should appear first
        self.assertLess(lb.index("U1"), lb.index("U2"))


class TestDailySummary(unittest.TestCase):
    def test_builds_summary(self):
        summary = build_daily_summary(SAMPLE_SCORES)
        self.assertIsNotNone(summary)
        self.assertIn("1302", summary)

    def test_empty_scores(self):
        self.assertIsNone(build_daily_summary({}))


class TestVs(unittest.TestCase):
    def test_head_to_head(self):
        vs = build_vs(SAMPLE_SCORES, "U1", "U2")
        self.assertIn("vs", vs)
        self.assertIn("U1", vs)
        self.assertIn("U2", vs)
        self.assertIn("wins", vs)

    def test_missing_player(self):
        vs = build_vs(SAMPLE_SCORES, "U1", "U99")
        self.assertIn("Need scores", vs)


class TestTiedRankings(unittest.TestCase):
    def test_daily_same_score_same_mode_is_tie(self):
        scores = {
            "100": {
                "U1": {"score": "5", "hard_mode": True, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "5", "hard_mode": True, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        summary = build_daily_summary(scores)
        self.assertEqual(summary.count("🥇"), 2)
        self.assertNotIn("🥈", summary)

    def test_daily_same_score_no_hard_mode_is_tie(self):
        scores = {
            "100": {
                "U1": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        summary = build_daily_summary(scores)
        self.assertEqual(summary.count("🥇"), 2)
        self.assertNotIn("🥈", summary)

    def test_daily_same_score_hard_mode_breaks_tie(self):
        scores = {
            "100": {
                "U1": {"score": "5", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "5", "hard_mode": True, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        summary = build_daily_summary(scores)
        self.assertEqual(summary.count("🥇"), 1)
        self.assertEqual(summary.count("🥈"), 1)
        # Hard mode player (U2) should rank above normal mode (U1)
        self.assertLess(summary.index("U2"), summary.index("U1"))

    def test_daily_different_scores_not_tied(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "5", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        summary = build_daily_summary(scores)
        self.assertEqual(summary.count("🥇"), 1)
        self.assertEqual(summary.count("🥈"), 1)

    def test_leaderboard_same_avg_is_tie(self):
        scores = {
            "100": {
                "U1": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        lb = build_leaderboard(scores, days=7)
        self.assertEqual(lb.count("🥇"), 2)
        self.assertNotIn("🥈", lb)

    def test_leaderboard_different_avg_not_tied(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "5", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        lb = build_leaderboard(scores, days=7)
        self.assertEqual(lb.count("🥇"), 1)
        self.assertEqual(lb.count("🥈"), 1)


class TestFetchWordleAnswer(unittest.TestCase):
    def test_fetches_known_date(self):
        from datetime import date
        answer = fetch_wordle_answer(date(2026, 3, 12))
        self.assertIsNotNone(answer)
        self.assertEqual(answer, "smell")

    def test_returns_none_on_invalid_date(self):
        from datetime import date
        answer = fetch_wordle_answer(date(1999, 1, 1))
        self.assertIsNone(answer)


class TestGetActivePlayers(unittest.TestCase):
    def test_finds_all_recent_players(self):
        active = get_active_players(SAMPLE_SCORES, lookback=14)
        self.assertEqual(active, {"U1", "U2"})

    def test_lookback_limits_scope(self):
        # U2 only played puzzles 1300 and 1301, not 1302
        # With lookback=1, only the latest puzzle (1302) is considered
        active = get_active_players(SAMPLE_SCORES, lookback=1)
        self.assertEqual(active, {"U1"})

    def test_empty_scores(self):
        active = get_active_players({})
        self.assertEqual(active, set())


class TestShameList(unittest.TestCase):
    def test_everyone_played(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        shame = build_shame_list(scores)
        self.assertIn("Everyone", shame)

    def test_someone_missing(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            },
            "101": {
                "U1": {"score": "5", "hard_mode": False, "timestamp": "2025-01-02T12:00:00"},
            },
        }
        shame = build_shame_list(scores)
        self.assertIn("U2", shame)
        self.assertNotIn("U1", shame)

    def test_empty_scores(self):
        shame = build_shame_list({})
        self.assertIn("No scores", shame)


class TestRivalry(unittest.TestCase):
    def test_close_rivalry_detected(self):
        # Two players with very close averages over 5+ games
        scores = {}
        for i in range(10):
            scores[str(100 + i)] = {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        rivalry = check_rivalry(scores)
        self.assertIsNotNone(rivalry)
        self.assertIn("Rivalry", rivalry)

    def test_no_rivalry_when_gap_is_large(self):
        scores = {}
        for i in range(10):
            scores[str(100 + i)] = {
                "U1": {"score": "2", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "6", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        rivalry = check_rivalry(scores)
        self.assertIsNone(rivalry)

    def test_not_enough_games(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        rivalry = check_rivalry(scores)
        self.assertIsNone(rivalry)


class TestSparkline(unittest.TestCase):
    def test_basic_sparkline(self):
        self.assertEqual(build_sparkline([1, 3, 5, 7]), "▁▃▅█")

    def test_single_score(self):
        self.assertEqual(build_sparkline([4]), "▄")

    def test_all_same(self):
        self.assertEqual(build_sparkline([3, 3, 3]), "▃▃▃")


class TestComeback(unittest.TestCase):
    def test_comeback_detected(self):
        scores = {
            "100": {"U1": {"score": "X", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}},
            "101": {"U1": {"score": "2", "hard_mode": False, "timestamp": "2025-01-02T12:00:00"}},
        }
        result = check_comeback(scores, "U1", "101")
        self.assertIsNotNone(result)
        # Should be from comeback_strong templates
        self.assertTrue(len(result) > 0)

    def test_no_comeback_when_both_good(self):
        scores = {
            "100": {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}},
            "101": {"U1": {"score": "2", "hard_mode": False, "timestamp": "2025-01-02T12:00:00"}},
        }
        self.assertIsNone(check_comeback(scores, "U1", "101"))

    def test_comeback_ok_detected(self):
        scores = {
            "100": {"U1": {"score": "5", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}},
            "101": {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-02T12:00:00"}},
        }
        result = check_comeback(scores, "U1", "101")
        self.assertIsNotNone(result)
        self.assertTrue(len(result) > 0)

    def test_no_comeback_on_first_puzzle(self):
        scores = {
            "100": {"U1": {"score": "2", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}},
        }
        self.assertIsNone(check_comeback(scores, "U1", "100"))


class TestPersonalBest(unittest.TestCase):
    def test_personal_best_detected(self):
        scores = {}
        # 10 games of 4s, then a 2
        for i in range(10):
            scores[str(100 + i)] = {"U1": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}
        scores["110"] = {"U1": {"score": "2", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}
        result = check_personal_best(scores, "U1")
        self.assertIsNotNone(result)
        self.assertIn("🏅", result)

    def test_no_personal_best_when_normal(self):
        scores = {}
        for i in range(10):
            scores[str(100 + i)] = {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}
        scores["110"] = {"U1": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}
        self.assertIsNone(check_personal_best(scores, "U1"))

    def test_not_enough_games(self):
        scores = {
            "100": {"U1": {"score": "1", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}},
        }
        self.assertIsNone(check_personal_best(scores, "U1"))


class TestGroupRecords(unittest.TestCase):
    def test_best_group_record(self):
        scores = {}
        for i in range(5):
            scores[str(100 + i)] = {
                "U1": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "5", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        # Latest puzzle has best group average
        scores["105"] = {
            "U1": {"score": "1", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
            "U2": {"score": "2", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
        }
        result = check_group_records(scores)
        self.assertIsNotNone(result)
        self.assertIn("record", result.lower())

    def test_no_record_when_average(self):
        scores = {}
        for i in range(6):
            scores[str(100 + i)] = {
                "U1": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        self.assertIsNone(check_group_records(scores))

    def test_not_enough_history(self):
        scores = {
            "100": {
                "U1": {"score": "1", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "1", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        self.assertIsNone(check_group_records(scores))


class TestGroupStreak(unittest.TestCase):
    def test_full_participation_streak(self):
        scores = {}
        for i in range(5):
            scores[str(100 + i)] = {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        self.assertEqual(get_group_streak(scores), 5)

    def test_broken_streak(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            },
            "101": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-02T12:00:00"},
            },
            "102": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-03T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-03T12:05:00"},
            },
        }
        # Latest puzzle (102) has both, but 101 is missing U2
        self.assertEqual(get_group_streak(scores), 1)

    def test_empty_scores(self):
        self.assertEqual(get_group_streak({}), 0)


class TestPuzzleMilestone(unittest.TestCase):
    def test_century_milestone(self):
        result = check_puzzle_milestone("1800")
        self.assertIsNotNone(result)
        self.assertIn("1800", result)

    def test_major_milestone(self):
        result = check_puzzle_milestone("2000")
        self.assertIsNotNone(result)
        self.assertIn("milestone", result.lower())

    def test_not_a_milestone(self):
        self.assertIsNone(check_puzzle_milestone("1728"))


class TestMonthlyRecap(unittest.TestCase):
    def test_builds_recap(self):
        # Puzzle numbers for March 2026: days since 2021-06-19
        # March 1, 2026 = day 1716, March 31, 2026 = day 1746
        scores = {}
        for i in range(1716, 1726):
            scores[str(i)] = {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2026-03-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2026-03-01T12:05:00"},
            }
        recap = build_monthly_recap(scores, 2026, 3)
        self.assertIsNotNone(recap)
        self.assertIn("March", recap)
        self.assertIn("Champion", recap)

    def test_no_data(self):
        self.assertIsNone(build_monthly_recap({}, 2026, 3))


class TestYearlyRecap(unittest.TestCase):
    def test_builds_recap(self):
        # Use puzzle numbers that fall in 2026
        scores = {}
        for i in range(1657, 1677):  # ~Jan 2026
            scores[str(i)] = {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2026-01-01T12:00:00"},
                "U2": {"score": "5", "hard_mode": False, "timestamp": "2026-01-01T12:05:00"},
            }
        recap = build_yearly_recap(scores, 2026)
        self.assertIsNotNone(recap)
        self.assertIn("2026", recap)
        self.assertIn("Player of the Year", recap)
        self.assertIn("Most consistent", recap)

    def test_no_data(self):
        self.assertIsNone(build_yearly_recap({}, 2026))


class TestCheckStreak(unittest.TestCase):
    def test_streak_at_3(self):
        scores = {}
        for i in range(3):
            scores[str(100 + i)] = {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}
        result = check_streak(scores, "U1")
        self.assertIsNotNone(result)
        self.assertIn("🔥", result)

    def test_streak_at_7(self):
        scores = {}
        for i in range(7):
            scores[str(100 + i)] = {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}
        result = check_streak(scores, "U1")
        self.assertIsNotNone(result)
        self.assertIn("🔥", result)

    def test_no_streak_at_4(self):
        scores = {}
        for i in range(4):
            scores[str(100 + i)] = {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}
        self.assertIsNone(check_streak(scores, "U1"))

    def test_no_streak_at_1(self):
        scores = {"100": {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}}
        self.assertIsNone(check_streak(scores, "U1"))


class TestSmartCommentary(unittest.TestCase):
    def test_returns_base_commentary(self):
        scores = {"100": {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}}
        replies = get_smart_commentary(scores, "U1", "100", "3", False)
        self.assertTrue(len(replies) >= 1)
        self.assertIn(replies[0], COMMENTARY["score_3"])

    def test_hard_mode_adds_context(self):
        scores = {"100": {"U1": {"score": "3", "hard_mode": True, "timestamp": "2025-01-01T12:00:00"}}}
        replies = get_smart_commentary(scores, "U1", "100", "3", True)
        self.assertTrue(len(replies) >= 2)
        hard_mode_found = any(r in COMMENTARY["hard_mode_good"] for r in replies)
        self.assertTrue(hard_mode_found)

    def test_hard_mode_fail(self):
        scores = {"100": {"U1": {"score": "X", "hard_mode": True, "timestamp": "2025-01-01T12:00:00"}}}
        replies = get_smart_commentary(scores, "U1", "100", "X", True)
        hard_mode_found = any(r in COMMENTARY["hard_mode_fail"] for r in replies)
        self.assertTrue(hard_mode_found)

    def test_limits_context_to_2(self):
        # Build scenario where many context triggers fire
        scores = {}
        for i in range(20):
            scores[str(100 + i)] = {"U1": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}
        scores["120"] = {"U1": {"score": "X", "hard_mode": False, "timestamp": "2025-01-02T12:00:00"}}
        scores["121"] = {"U1": {"score": "1", "hard_mode": True, "timestamp": "2025-01-03T12:00:00"}}
        replies = get_smart_commentary(scores, "U1", "121", "1", True)
        # base (1) + max 2 context = 3 max
        self.assertLessEqual(len(replies), 3)
        self.assertTrue(len(replies) >= 1)

    def test_fail_gets_commentary(self):
        scores = {"100": {"U1": {"score": "X", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}}
        replies = get_smart_commentary(scores, "U1", "100", "X", False)
        self.assertTrue(len(replies) >= 1)
        self.assertIn(replies[0], COMMENTARY["score_x"])

    def test_no_hard_mode_no_extra(self):
        scores = {"100": {"U1": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}}
        replies = get_smart_commentary(scores, "U1", "100", "4", False)
        # Only base commentary, no contextual triggers
        self.assertEqual(len(replies), 1)


class TestRankIcon(unittest.TestCase):
    def test_top_three(self):
        self.assertEqual(rank_icon(0), "🥇")
        self.assertEqual(rank_icon(1), "🥈")
        self.assertEqual(rank_icon(2), "🥉")

    def test_beyond_ten(self):
        self.assertEqual(rank_icon(15), "16.")


if __name__ == "__main__":
    unittest.main()
