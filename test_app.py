"""Tests for Wordle bot core logic (no Slack connection needed)."""

import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import logic
from logic import (
    COMMENTARY,
    HARD_MODE_RE,
    SUPPLEMENTAL,
    WORDLE_RE,
    _apply_diacritics,
    _format_conditions,
    build_daily_summary,
    build_leaderboard,
    build_shame_list,
    build_sparkline,
    build_monthly_recap,
    build_vs,
    build_yearly_recap,
    calc_streak,
    check_comeback,
    check_group_records,
    check_personal_best,
    check_puzzle_milestone,
    check_rivalry,
    check_streak,
    fetch_wordle_answer,
    get_active_players,
    get_commentary,
    get_group_streak,
    get_smart_commentary,
    get_user_scores,
    get_user_stats,
    rank_icon,
)


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
        current, best = calc_streak([100, 101, 102, 103, 200, 201])
        self.assertEqual(current, 2)
        self.assertEqual(best, 4)


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
        stats = get_user_stats(SAMPLE_SCORES, "U1", today_puzzle=1303)
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
        shame, has_missing = build_shame_list(scores, today_puzzle=100)
        self.assertIn("Everyone", shame)
        self.assertFalse(has_missing)

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
        shame, has_missing = build_shame_list(scores, today_puzzle=101)
        self.assertIn("U2", shame)
        self.assertNotIn("U1", shame)
        self.assertTrue(has_missing)

    def test_empty_scores(self):
        shame, has_missing = build_shame_list({})
        self.assertIn("No scores", shame)
        self.assertFalse(has_missing)


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


class TestSupplementalLoader(unittest.TestCase):
    def test_supplemental_loads(self):
        self.assertIsInstance(SUPPLEMENTAL, dict)

    def test_has_score_keys(self):
        for key in ["score_1", "score_2", "score_3", "score_4", "score_5", "score_6", "score_x"]:
            self.assertIn(key, SUPPLEMENTAL, f"Missing key: {key}")
            self.assertTrue(len(SUPPLEMENTAL[key]) >= 3, f"Too few templates for {key}")

    def test_has_morning_evening(self):
        self.assertIn("morning_briefing", SUPPLEMENTAL)
        self.assertIn("evening_briefing", SUPPLEMENTAL)

    def test_has_shame_and_all_played(self):
        self.assertIn("shame", SUPPLEMENTAL)
        self.assertIn("all_played", SUPPLEMENTAL)
        for tmpl in SUPPLEMENTAL["shame"]:
            self.assertIn("{names}", tmpl)

    def test_has_all_moon_phases(self):
        self.assertIn("moon_phase", SUPPLEMENTAL)
        for phase in ["new", "waxing_crescent", "first_quarter", "waxing_gibbous",
                      "full", "waning_gibbous", "last_quarter", "waning_crescent"]:
            self.assertIn(phase, SUPPLEMENTAL["moon_phase"], f"Missing phase: {phase}")
            self.assertTrue(len(SUPPLEMENTAL["moon_phase"][phase]) >= 1, f"No templates for {phase}")

    def test_sea_temperature_templates_have_placeholder(self):
        self.assertIn("sea_temperature", SUPPLEMENTAL)
        self.assertTrue(len(SUPPLEMENTAL["sea_temperature"]) >= 1)
        for tmpl in SUPPLEMENTAL["sea_temperature"]:
            self.assertIn("{temp}", tmpl)


class TestApplyDiacritics(unittest.TestCase):
    def test_adds_combining_chars(self):
        result = _apply_diacritics("TEST")
        self.assertGreater(len(result), 4)

    def test_preserves_base_text(self):
        import unicodedata
        result = _apply_diacritics("HELLO")
        base = "".join(c for c in result if unicodedata.category(c) != "Mn")
        self.assertEqual(base, "HELLO")

    def test_empty_string(self):
        self.assertEqual(_apply_diacritics(""), "")

    def test_non_alpha_unchanged(self):
        result = _apply_diacritics("123")
        self.assertEqual(result, "123")


class TestFormatConditions(unittest.TestCase):
    def test_formats_full_data(self):
        data = {
            "current": {
                "wave_height": 1.5,
                "swell_wave_height": 1.2,
                "swell_wave_period": 9.5,
                "swell_wave_direction": 280,
            }
        }
        result = _format_conditions(data, "Mavericks")
        self.assertIn("Mavericks", result)
        self.assertIn("1.2m", result)
        self.assertIn("9.5s", result)

    def test_wave_height_only(self):
        data = {"current": {"wave_height": 2.0}}
        result = _format_conditions(data, "Ocean Beach")
        self.assertIn("Ocean Beach", result)
        self.assertIn("2.0m", result)

    def test_missing_current(self):
        result = _format_conditions({}, "Bolinas")
        self.assertIn("No data", result)

    def test_direction_conversion(self):
        # 270 degrees = W
        data = {
            "current": {
                "wave_height": 1.0,
                "swell_wave_height": 0.8,
                "swell_wave_period": 8.0,
                "swell_wave_direction": 270,
            }
        }
        result = _format_conditions(data, "Fort Point")
        self.assertIn("W", result)

    def test_includes_sea_temperature_line(self):
        data = {
            "current": {
                "wave_height": 1.5,
                "swell_wave_height": 1.2,
                "swell_wave_period": 9.5,
                "swell_wave_direction": 280,
                "sea_surface_temperature": 14.43,
            }
        }
        result = _format_conditions(data, "Mavericks")
        self.assertIn("14.4°C", result)

    def test_no_temp_line_when_temp_missing(self):
        data = {"current": {"wave_height": 2.0}}
        result = _format_conditions(data, "Ocean Beach")
        self.assertNotIn("°C", result)


class TestMoonPhase(unittest.TestCase):
    KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14)
    SYNODIC = 29.530588853
    PHASES = ["new", "waxing_crescent", "first_quarter", "waxing_gibbous",
              "full", "waning_gibbous", "last_quarter", "waning_crescent"]

    def test_known_new_moon(self):
        self.assertEqual(logic._moon_phase(self.KNOWN_NEW_MOON), "new")

    def test_first_quarter_at_quarter_cycle(self):
        dt = self.KNOWN_NEW_MOON + timedelta(days=self.SYNODIC / 4)
        self.assertEqual(logic._moon_phase(dt), "first_quarter")

    def test_full_at_half_cycle(self):
        dt = self.KNOWN_NEW_MOON + timedelta(days=self.SYNODIC / 2)
        self.assertEqual(logic._moon_phase(dt), "full")

    def test_last_quarter_at_three_quarter_cycle(self):
        dt = self.KNOWN_NEW_MOON + timedelta(days=self.SYNODIC * 3 / 4)
        self.assertEqual(logic._moon_phase(dt), "last_quarter")

    def test_wraps_after_many_cycles(self):
        dt = self.KNOWN_NEW_MOON + timedelta(days=self.SYNODIC * 100)
        self.assertEqual(logic._moon_phase(dt), "new")

    def test_always_returns_valid_phase_key(self):
        for offset in range(31):
            phase = logic._moon_phase(datetime(2026, 7, 1) + timedelta(days=offset))
            self.assertIn(phase, self.PHASES)


class TestAltModeCommentary(unittest.TestCase):
    def setUp(self):
        logic.activate_alt_mode(None)

    def tearDown(self):
        logic._deactivate_alt_mode()

    def test_alt_score_commentary(self):
        for score in ["1", "2", "3", "4", "5", "6", "X"]:
            c = get_commentary(score)
            self.assertIsNotNone(c, f"No alt commentary for score {score}")
            key = f"score_{score}" if score != "X" else "score_x"
            self.assertIn(c, SUPPLEMENTAL[key])

    def test_alt_smart_commentary_base(self):
        scores = {"100": {"U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"}}}
        replies = get_smart_commentary(scores, "U1", "100", "3", False)
        self.assertTrue(len(replies) >= 1)
        self.assertIn(replies[0], SUPPLEMENTAL["score_3"])

    def test_alt_hard_mode(self):
        scores = {"100": {"U1": {"score": "3", "hard_mode": True, "timestamp": "2025-01-01T12:00:00"}}}
        replies = get_smart_commentary(scores, "U1", "100", "3", True)
        self.assertTrue(len(replies) >= 2)
        hard_found = any(r in SUPPLEMENTAL.get("hard_mode_good", []) for r in replies)
        self.assertTrue(hard_found)

    def test_alt_shame(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            },
            "101": {
                "U1": {"score": "5", "hard_mode": False, "timestamp": "2025-01-02T12:00:00"},
            },
        }
        shame, has_missing = build_shame_list(scores, today_puzzle=101)
        self.assertTrue(has_missing)
        has_crab_emoji = "\U0001f980" in shame or "\U0001f30a" in shame
        self.assertTrue(has_crab_emoji, f"Shame message missing crab/wave emoji: {shame}")


class TestAltModeDailySummary(unittest.TestCase):
    def setUp(self):
        logic.activate_alt_mode(None)

    def tearDown(self):
        logic._deactivate_alt_mode()

    def test_alt_daily_summary_header(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        summary = build_daily_summary(scores)
        self.assertIsNotNone(summary)
        self.assertNotIn("Wordle 100 Results", summary)

    def test_alt_daily_summary_difficulty(self):
        scores = {
            "100": {
                "U1": {"score": "5", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "6", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        summary = build_daily_summary(scores)
        normal_texts = ["easy one today", "solid challenge", "tough one today", "brutal. absolute brutality."]
        has_normal = any(t in summary for t in normal_texts)
        self.assertFalse(has_normal, "Should use alt difficulty text in alt mode")


class TestShameListToday(unittest.TestCase):
    def test_nobody_played_today_shames_active_players(self):
        scores = {
            "100": {
                "U1": {"score": "3", "hard_mode": False, "timestamp": "2025-01-01T12:00:00"},
                "U2": {"score": "4", "hard_mode": False, "timestamp": "2025-01-01T12:05:00"},
            }
        }
        shame, has_missing = build_shame_list(scores, today_puzzle=101)
        self.assertTrue(has_missing)
        self.assertIn("U1", shame)
        self.assertIn("U2", shame)


class TestStreakDecay(unittest.TestCase):
    def test_current_streak_zeroed_when_stale(self):
        stats = get_user_stats(SAMPLE_SCORES, "U1", today_puzzle=1310)
        self.assertEqual(stats["current_streak"], 0)
        self.assertEqual(stats["best_streak"], 3)

    def test_current_streak_survives_when_played_yesterday(self):
        stats = get_user_stats(SAMPLE_SCORES, "U1", today_puzzle=1303)
        self.assertEqual(stats["current_streak"], 3)


class TestAltModeExpiry(unittest.TestCase):
    def tearDown(self):
        logic._deactivate_alt_mode()

    def test_expired_alt_mode_reverts_to_normal_commentary(self):
        logic._alt_active = True
        logic._alt_activated_at = datetime.now() - timedelta(hours=25)
        c = get_commentary("3")
        self.assertIn(c, COMMENTARY["score_3"])
        self.assertFalse(logic._alt_active)

    def test_fresh_alt_mode_still_active(self):
        logic._alt_active = True
        logic._alt_activated_at = datetime.now() - timedelta(hours=23)
        c = get_commentary("3")
        self.assertIn(c, SUPPLEMENTAL["score_3"])


class TempDataDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = logic.DATA_DIR
        self._old_scores = logic.SCORES_FILE
        logic.DATA_DIR = Path(self._tmp.name)
        logic.SCORES_FILE = logic.DATA_DIR / "scores.json"

    def tearDown(self):
        logic.DATA_DIR = self._old_dir
        logic.SCORES_FILE = self._old_scores
        self._tmp.cleanup()


class TestRecordScoreConcurrency(TempDataDirTestCase):
    def test_simultaneous_scores_all_recorded(self):
        barrier = threading.Barrier(8)

        def submit(uid):
            barrier.wait()
            logic.record_score(uid, "1500", "3")

        threads = [threading.Thread(target=submit, args=(f"U{i}",)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(logic.load_scores()["1500"]), 8)


class TestRecordScoresBulk(TempDataDirTestCase):
    def test_bulk_skips_existing_and_writes_once(self):
        logic.record_score("U1", "1500", "3")
        saves = []
        real_save = logic.save_scores

        def counting_save(scores):
            saves.append(1)
            real_save(scores)

        logic.save_scores = counting_save
        try:
            count = logic.record_scores_bulk([
                ("U1", "1500", "4", False),
                ("U2", "1500", "2", True),
                ("U3", "1501", "X", False),
            ])
        finally:
            logic.save_scores = real_save

        self.assertEqual(count, 2)
        self.assertEqual(len(saves), 1)
        scores = logic.load_scores()
        self.assertEqual(scores["1500"]["U1"]["score"], "3")
        self.assertEqual(scores["1500"]["U2"]["score"], "2")
        self.assertTrue(scores["1500"]["U2"]["hard_mode"])
        self.assertEqual(scores["1501"]["U3"]["score"], "X")


class FakePagingClient:
    """Minimal stand-in for Slack's users_list cursor pagination."""

    def __init__(self, pages):
        self._pages = pages

    def users_list(self, **kwargs):
        cursor = kwargs.get("cursor")
        idx = int(cursor) if cursor else 0
        nxt = str(idx + 1) if idx + 1 < len(self._pages) else ""
        return {
            "members": self._pages[idx],
            "response_metadata": {"next_cursor": nxt},
        }


class TestLookupUserByName(unittest.TestCase):
    def test_finds_user_on_a_later_page(self):
        client = FakePagingClient([
            [{"id": "U1", "name": "alice", "profile": {}}],
            [{"id": "U2", "name": "bob", "profile": {"display_name": "Bobby", "real_name": "Bob B"}}],
        ])
        self.assertEqual(logic.lookup_user_by_name(client, "bobby"), "U2")

    def test_unknown_name_returns_none(self):
        client = FakePagingClient([[{"id": "U1", "name": "alice", "profile": {}}]])
        self.assertIsNone(logic.lookup_user_by_name(client, "zed"))

    def test_skips_bots_and_deleted(self):
        client = FakePagingClient([[
            {"id": "U3", "name": "carol", "is_bot": True, "profile": {}},
            {"id": "U4", "name": "carol", "deleted": True, "profile": {}},
            {"id": "U5", "name": "carol", "profile": {}},
        ]])
        self.assertEqual(logic.lookup_user_by_name(client, "carol"), "U5")


if __name__ == "__main__":
    unittest.main()
