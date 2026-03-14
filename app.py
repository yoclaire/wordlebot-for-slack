"""
Wordle score tracker for Slack.

Watches a channel for Wordle share pastes, parses scores,
tracks stats, posts leaderboards, and talks trash.
"""

import os
import re
import json
import random
import logging
import calendar
import threading
import urllib.request
from datetime import datetime, timedelta, date
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = App(token=os.environ["SLACK_BOT_TOKEN"])

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(exist_ok=True)
SCORES_FILE = DATA_DIR / "scores.json"
CONFIG_FILE = DATA_DIR / "config.json"

# Wordle share format: "Wordle 1,234 3/6" or "Wordle 1,234 X/6"
WORDLE_RE = re.compile(r"Wordle\s+([\d,]+)\s+([X1-6])/6", re.IGNORECASE)
# Hard mode indicator: asterisk after score
HARD_MODE_RE = re.compile(r"Wordle\s+[\d,]+\s+[X1-6]/6\*", re.IGNORECASE)

RANK_ICONS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# Load commentary templates from external file
COMMENTARY_FILE = Path(__file__).parent / "commentary.json"
COMMENTARY = json.loads(COMMENTARY_FILE.read_text()) if COMMENTARY_FILE.exists() else {}

MILESTONES = [10, 25, 50, 100, 200, 365, 500, 1000]

ACHIEVEMENTS = {
    "first_solve": ("🟩 First Solve", "recorded your first Wordle"),
    "perfect": ("💎 Perfect", "got a 1/6"),
    "century": ("💯 Century Club", "played 100 games"),
    "streak_7": ("🔥 On Fire", "7-day streak"),
    "streak_30": ("🌋 Unstoppable", "30-day streak"),
    "streak_100": ("⚡ Legendary", "100-day streak"),
    "sub_3_avg": ("🧠 Big Brain", "sub-3.0 average over 10+ games"),
    "survivor_5": ("🪦 Five Lives", "survived 5 X's and kept playing"),
    "hard_mode_10": ("⭐ Hard Mode Hero", "10 hard mode games"),
    "no_fails_20": ("🛡️ Flawless", "20 games without an X"),
}


# --- Data helpers ---


def fetch_wordle_answer(puzzle_date: date) -> str | None:
    """Fetch the Wordle answer for a given date from the NYT API."""
    url = f"https://www.nytimes.com/svc/wordle/v2/{puzzle_date.isoformat()}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wordlebot"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("solution")
    except Exception as e:
        logging.warning(f"Could not fetch Wordle answer for {puzzle_date}: {e}")
        return None


def lookup_user_by_name(name: str) -> str | None:
    """Look up a Slack user ID by display name, username, or real name."""
    try:
        resp = app.client.users_list()
        for member in resp.get("members", []):
            if member.get("deleted") or member.get("is_bot"):
                continue
            profile = member.get("profile", {})
            if name.lower() in (
                member.get("name", "").lower(),
                profile.get("display_name", "").lower(),
                profile.get("real_name", "").lower(),
            ):
                return member["id"]
    except Exception as e:
        logging.warning(f"Could not look up user '{name}': {e}")
    return None

def load_scores() -> dict:
    if SCORES_FILE.exists():
        return json.loads(SCORES_FILE.read_text())
    return {}


def save_scores(scores: dict):
    tmp = str(SCORES_FILE) + ".tmp"
    Path(tmp).write_text(json.dumps(scores, indent=2))
    os.replace(tmp, SCORES_FILE)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(config: dict):
    tmp = str(CONFIG_FILE) + ".tmp"
    Path(tmp).write_text(json.dumps(config, indent=2))
    os.replace(tmp, CONFIG_FILE)


def record_score(user_id: str, puzzle_num: str, score: str, hard_mode: bool = False) -> str | None:
    """Record a score. Returns the score string or None if already recorded."""
    scores = load_scores()
    key = puzzle_num

    if key not in scores:
        scores[key] = {}

    if user_id in scores[key]:
        return None

    scores[key][user_id] = {
        "score": score,
        "hard_mode": hard_mode,
        "timestamp": datetime.now().isoformat(),
    }
    save_scores(scores)
    return score


def get_user_scores(scores: dict, user_id: str) -> tuple[list[int], list[int]]:
    """Return (score_values, puzzle_numbers) for a user, sorted by puzzle number."""
    user_scores = []
    puzzles_played = []
    for puzzle_num in sorted(scores.keys(), key=lambda x: int(x.replace(",", ""))):
        if user_id in scores[puzzle_num]:
            s = scores[puzzle_num][user_id]["score"]
            user_scores.append(7 if s == "X" else int(s))
            puzzles_played.append(int(puzzle_num.replace(",", "")))
    return user_scores, puzzles_played


def calc_streak(puzzles_played: list[int]) -> tuple[int, int]:
    """Return (current_streak, best_streak) from sorted puzzle numbers."""
    if not puzzles_played:
        return 0, 0
    current = 1
    best = 1
    for i in range(len(puzzles_played) - 1, 0, -1):
        if puzzles_played[i] - puzzles_played[i - 1] == 1:
            current += 1
            best = max(best, current)
        else:
            break
    best = max(best, current)
    return current, best


def get_user_stats(scores: dict, user_id: str) -> dict | None:
    """Get comprehensive stats for a single user."""
    user_scores, puzzles_played = get_user_scores(scores, user_id)
    if not user_scores:
        return None

    current_streak, best_streak = calc_streak(puzzles_played)

    hard_mode_count = sum(
        1 for p in scores.values()
        if user_id in p and p[user_id].get("hard_mode", False)
    )

    return {
        "games": len(user_scores),
        "avg": sum(user_scores) / len(user_scores),
        "best": min(user_scores),
        "worst": max(user_scores),
        "fails": user_scores.count(7),
        "wins": len(user_scores) - user_scores.count(7),
        "current_streak": current_streak,
        "best_streak": best_streak,
        "distribution": {str(i): user_scores.count(i) for i in range(1, 7)} | {"X": user_scores.count(7)},
        "hard_mode_count": hard_mode_count,
        "recent_5": user_scores[-5:] if len(user_scores) >= 5 else user_scores,
    }


# --- Commentary & alerts ---

def get_commentary(score: str) -> str | None:
    key = f"score_{score}" if score != "X" else "score_x"
    templates = COMMENTARY.get(key, [])
    return random.choice(templates) if templates else None


def check_milestone(scores: dict, user_id: str) -> str | None:
    count = sum(1 for p in scores.values() if user_id in p)
    if count in MILESTONES:
        return f"🎉 <@{user_id}> just logged Wordle #{count}!"
    return None


def check_streak(scores: dict, user_id: str) -> str | None:
    _, puzzles = get_user_scores(scores, user_id)
    current, _ = calc_streak(puzzles)
    if current >= 7 and current % 7 == 0:
        key = "streak_epic" if current >= 14 else "streak_hot"
        templates = COMMENTARY.get(key, [])
        if templates:
            return f"🔥 <@{user_id}> — " + random.choice(templates).format(streak=current)
        return f"🔥 <@{user_id}> is on a *{current}-day streak*!"
    if current == 3:
        templates = COMMENTARY.get("streak_building", [])
        if templates:
            return f"🔥 <@{user_id}> — " + random.choice(templates).format(streak=current)
        return f"🔥 <@{user_id}> — 3-day streak going!"
    return None


def check_hot_cold(scores: dict, user_id: str) -> str | None:
    """Detect hot hand or cold streak vs overall average."""
    stats = get_user_stats(scores, user_id)
    if not stats or stats["games"] < 10:
        return None
    recent = stats["recent_5"]
    if len(recent) < 5:
        return None
    recent_avg = sum(recent) / len(recent)
    overall_avg = stats["avg"]
    diff = overall_avg - recent_avg
    if diff >= 1.0:
        templates = COMMENTARY.get("hot_hand", [])
        if templates:
            return f"📈 <@{user_id}> " + random.choice(templates).format(recent_avg=recent_avg, overall_avg=overall_avg)
        return f"📈 <@{user_id}> is heating up — *{recent_avg:.1f}* avg recently vs *{overall_avg:.1f}* overall"
    if diff <= -1.0:
        templates = COMMENTARY.get("cold_spell", [])
        if templates:
            return f"📉 <@{user_id}> " + random.choice(templates).format(recent_avg=recent_avg, overall_avg=overall_avg)
        return f"📉 <@{user_id}> going through it — *{recent_avg:.1f}* avg recently vs *{overall_avg:.1f}* overall"
    return None


def check_achievements(scores: dict, user_id: str) -> list[str]:
    """Check for newly earned achievements."""
    config = load_config()
    earned = config.get("achievements", {}).get(user_id, [])
    stats = get_user_stats(scores, user_id)
    if not stats:
        return []

    new_achievements = []

    checks = [
        ("first_solve", stats["games"] >= 1),
        ("perfect", stats["distribution"].get("1", 0) >= 1),
        ("century", stats["games"] >= 100),
        ("streak_7", stats["best_streak"] >= 7),
        ("streak_30", stats["best_streak"] >= 30),
        ("streak_100", stats["best_streak"] >= 100),
        ("sub_3_avg", stats["games"] >= 10 and stats["avg"] < 3.0),
        ("survivor_5", stats["fails"] >= 5),
        ("hard_mode_10", stats["hard_mode_count"] >= 10),
    ]

    # Check no_fails_20: 20 consecutive non-X games
    user_scores, _ = get_user_scores(scores, user_id)
    consecutive_wins = 0
    max_consecutive_wins = 0
    for s in user_scores:
        if s < 7:
            consecutive_wins += 1
            max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
        else:
            consecutive_wins = 0
    checks.append(("no_fails_20", max_consecutive_wins >= 20))

    for key, condition in checks:
        if condition and key not in earned:
            earned.append(key)
            emoji, desc = ACHIEVEMENTS[key]
            new_achievements.append(f"{emoji} *Achievement unlocked:* {desc}!")

    if new_achievements:
        if "achievements" not in config:
            config["achievements"] = {}
        config["achievements"][user_id] = earned
        save_config(config)

    return new_achievements


def check_rivalry(scores: dict) -> str | None:
    """Detect close rivalries over the last 30 puzzles."""
    all_puzzles = sorted(scores.keys(), key=lambda x: int(x.replace(",", "")))
    recent = all_puzzles[-30:] if len(all_puzzles) > 30 else all_puzzles

    user_avgs: dict[str, float] = {}
    user_games: dict[str, int] = {}
    for puzzle in recent:
        for uid, data in scores[puzzle].items():
            s = data["score"]
            val = 7 if s == "X" else int(s)
            if uid not in user_avgs:
                user_avgs[uid] = 0
                user_games[uid] = 0
            user_avgs[uid] += val
            user_games[uid] += 1

    # Only consider players with 5+ games
    qualified = {uid: user_avgs[uid] / user_games[uid] for uid, g in user_games.items() if g >= 5}
    if len(qualified) < 2:
        return None

    ranked = sorted(qualified.items(), key=lambda x: x[1])
    for i in range(len(ranked) - 1):
        uid1, avg1 = ranked[i]
        uid2, avg2 = ranked[i + 1]
        if abs(avg1 - avg2) <= 0.15:
            return (
                f"⚔️ *Rivalry alert!* <@{uid1}> ({avg1:.2f}) vs "
                f"<@{uid2}> ({avg2:.2f}) — neck and neck over the last 30 puzzles"
            )
    return None


# --- Display builders ---

def rank_icon(i: int) -> str:
    return RANK_ICONS[i] if i < len(RANK_ICONS) else f"{i + 1}."


def build_leaderboard(scores: dict, days: int = 7) -> str:
    all_puzzles = sorted(scores.keys(), key=lambda x: int(x.replace(",", "")))
    recent = all_puzzles[-days:] if len(all_puzzles) > days else all_puzzles

    if not recent:
        return "No scores recorded yet!"

    user_stats: dict[str, list[int]] = {}
    for puzzle in recent:
        for user_id, data in scores[puzzle].items():
            if user_id not in user_stats:
                user_stats[user_id] = []
            s = data["score"]
            user_stats[user_id].append(7 if s == "X" else int(s))

    if not user_stats:
        return "No scores recorded yet!"

    ranked = sorted(user_stats.items(), key=lambda x: sum(x[1]) / len(x[1]))

    lines = [f"*Wordle Leaderboard* (last {len(recent)} puzzles)\n"]
    prev_avg = None
    current_rank = 0
    for i, (user_id, scores_list) in enumerate(ranked):
        avg = sum(scores_list) / len(scores_list)
        rounded = round(avg, 1)
        if rounded != prev_avg:
            current_rank = i
            prev_avg = rounded
        games = len(scores_list)
        best = min(scores_list)
        fails = scores_list.count(7)
        best_str = "X" if best == 7 else str(best)
        lines.append(
            f"{rank_icon(current_rank)} <@{user_id}> — avg *{avg:.1f}* "
            f"({games} games, best: {best_str}"
            f"{f', {fails} fails' if fails else ''})"
        )

    return "\n".join(lines)


def build_daily_summary(scores: dict) -> str | None:
    if not scores:
        return None

    latest = max(scores.keys(), key=lambda x: int(x.replace(",", "")))
    puzzle_scores = scores[latest]
    if not puzzle_scores:
        return None

    ranked = sorted(
        puzzle_scores.items(),
        key=lambda x: (
            7 if x[1]["score"] == "X" else int(x[1]["score"]),
            not x[1].get("hard_mode", False),
        ),
    )

    lines = [f"*Wordle {latest} Results*\n"]
    prev_key = None
    current_rank = 0
    for i, (user_id, data) in enumerate(ranked):
        score_val = 7 if data["score"] == "X" else int(data["score"])
        hm = data.get("hard_mode", False)
        rank_key = (score_val, hm)
        if rank_key != prev_key:
            current_rank = i
            prev_key = rank_key
        hm_str = " ⭐" if hm else ""
        lines.append(f"{rank_icon(current_rank)} <@{user_id}> — {data['score']}/6{hm_str}")

    # Group difficulty assessment
    all_scores = [7 if d["score"] == "X" else int(d["score"]) for d in puzzle_scores.values()]
    if all_scores:
        avg = sum(all_scores) / len(all_scores)
        if avg <= 3.0:
            lines.append("\n🟢 easy one today")
        elif avg <= 4.0:
            lines.append("\n🟡 solid challenge")
        elif avg <= 5.0:
            lines.append("\n🟠 tough one today")
        else:
            lines.append("\n🔴 brutal. absolute brutality.")

    return "\n".join(lines)


def build_personal_stats(scores: dict, user_id: str) -> str:
    stats = get_user_stats(scores, user_id)
    if not stats:
        return "No scores recorded for you yet!"

    dist_lines = []
    max_count = max(stats["distribution"].values()) or 1
    for label in ["1", "2", "3", "4", "5", "6", "X"]:
        count = stats["distribution"].get(label, 0)
        bar_len = round((count / max_count) * 12) if count else 0
        bar = "█" * bar_len
        dist_lines.append(f"  {label}: {bar} {count}")

    hm_str = f"\n⭐ Hard mode games: {stats['hard_mode_count']}" if stats["hard_mode_count"] else ""

    # Show earned achievements
    config = load_config()
    earned = config.get("achievements", {}).get(user_id, [])
    if earned:
        badges = " ".join(ACHIEVEMENTS[k][0].split()[0] for k in earned if k in ACHIEVEMENTS)
        achievement_str = f"\n\n*Badges:* {badges}"
    else:
        achievement_str = ""

    # Recent form with sparkline
    user_scores, _ = get_user_scores(scores, user_id)
    recent = stats["recent_5"]
    if len(recent) >= 5:
        recent_avg = sum(recent) / len(recent)
        trend = "📈" if recent_avg < stats["avg"] else "📉" if recent_avg > stats["avg"] else "➡️"
        form_str = f"\n{trend} Recent form (last 5): *{recent_avg:.1f}* avg"
    else:
        form_str = ""

    # Sparkline of last 14 scores
    spark_scores = user_scores[-14:] if len(user_scores) >= 14 else user_scores
    sparkline_str = f"\n\n*Last {len(spark_scores)} games:* `{build_sparkline(spark_scores)}`" if len(spark_scores) >= 3 else ""

    return (
        f"*Your Wordle Stats*\n\n"
        f"Games: *{stats['games']}* | "
        f"Avg: *{stats['avg']:.1f}* | "
        f"Best: *{stats['best'] if stats['best'] < 7 else 'X'}* | "
        f"Worst: *{stats['worst'] if stats['worst'] < 7 else 'X'}*\n"
        f"Win rate: *{stats['wins'] / stats['games'] * 100:.0f}%* | "
        f"Current streak: *{stats['current_streak']}* | "
        f"Best streak: *{stats['best_streak']}*"
        f"{hm_str}{form_str}{achievement_str}{sparkline_str}\n"
        f"\n*Distribution:*\n```\n" + "\n".join(dist_lines) + "\n```"
    )


def build_vs(scores: dict, user1: str, user2: str) -> str:
    s1 = get_user_stats(scores, user1)
    s2 = get_user_stats(scores, user2)
    if not s1 or not s2:
        return "Need scores from both players to compare!"

    head_to_head = 0
    u1_wins = 0
    u2_wins = 0
    ties = 0
    for puzzle in scores:
        if user1 in scores[puzzle] and user2 in scores[puzzle]:
            head_to_head += 1
            s1_score = 7 if scores[puzzle][user1]["score"] == "X" else int(scores[puzzle][user1]["score"])
            s2_score = 7 if scores[puzzle][user2]["score"] == "X" else int(scores[puzzle][user2]["score"])
            if s1_score < s2_score:
                u1_wins += 1
            elif s2_score < s1_score:
                u2_wins += 1
            else:
                ties += 1

    # Who's got the edge?
    if u1_wins > u2_wins:
        verdict = f"<@{user1}> leads the series"
    elif u2_wins > u1_wins:
        verdict = f"<@{user2}> leads the series"
    else:
        verdict = "dead even"

    lines = [
        f"*<@{user1}> vs <@{user2}>*\n",
        f"Head-to-head: *{head_to_head}* games — {verdict}",
        f"  <@{user1}>: *{u1_wins}* wins",
        f"  <@{user2}>: *{u2_wins}* wins",
        f"  Ties: *{ties}*\n",
        f"*{'Stat':<15s}  {'':>10s}  {'':>10s}*",
        f"  {'Avg':<15s}  {s1['avg']:>10.1f}  {s2['avg']:>10.1f}",
        f"  {'Games':<15s}  {s1['games']:>10d}  {s2['games']:>10d}",
        f"  {'Best':<15s}  {s1['best']:>10d}  {s2['best']:>10d}",
        f"  {'Win %':<15s}  {s1['wins']/s1['games']*100:>9.0f}%  {s2['wins']/s2['games']*100:>9.0f}%",
        f"  {'Best streak':<15s}  {s1['best_streak']:>10d}  {s2['best_streak']:>10d}",
    ]

    return "\n".join(lines)


def build_hardest_puzzles(scores: dict, count: int = 5) -> str:
    """Show the hardest/easiest puzzles by group average."""
    if not scores:
        return "No scores recorded yet!"

    puzzle_avgs = []
    for puzzle_num, players in scores.items():
        vals = [7 if d["score"] == "X" else int(d["score"]) for d in players.values()]
        if len(vals) >= 2:  # need at least 2 players to be meaningful
            puzzle_avgs.append((puzzle_num, sum(vals) / len(vals), len(vals)))

    if not puzzle_avgs:
        return "Not enough data yet (need 2+ players per puzzle)."

    hardest = sorted(puzzle_avgs, key=lambda x: -x[1])[:count]
    easiest = sorted(puzzle_avgs, key=lambda x: x[1])[:count]

    lines = ["*Hardest Puzzles* 🟥\n"]
    for puzzle, avg, players in hardest:
        lines.append(f"  Wordle {puzzle} — avg *{avg:.1f}* ({players} players)")

    lines.append("\n*Easiest Puzzles* 🟩\n")
    for puzzle, avg, players in easiest:
        lines.append(f"  Wordle {puzzle} — avg *{avg:.1f}* ({players} players)")

    return "\n".join(lines)


def get_active_players(scores: dict, lookback: int = 14) -> set[str]:
    all_puzzles = sorted(scores.keys(), key=lambda x: int(x.replace(",", "")))
    recent = all_puzzles[-lookback:] if len(all_puzzles) > lookback else all_puzzles
    players = set()
    for puzzle in recent:
        players.update(scores[puzzle].keys())
    return players


def build_shame_list(scores: dict) -> str:
    if not scores:
        return "No scores recorded yet!"

    latest = max(scores.keys(), key=lambda x: int(x.replace(",", "")))
    today_players = set(scores[latest].keys())
    active = get_active_players(scores)
    missing = active - today_players

    if not missing:
        return "Everyone's played today! 🎉"

    names = ", ".join(f"<@{uid}>" for uid in missing)
    templates = COMMENTARY.get("shame", ["{names}: play wordle already"])
    return random.choice(templates).format(names=names)


def build_sparkline(score_values: list[int]) -> str:
    """Build a text sparkline from score values. Lower bars = better scores."""
    blocks = {1: "▁", 2: "▂", 3: "▃", 4: "▄", 5: "▅", 6: "▆", 7: "█"}
    return "".join(blocks.get(s, "█") for s in score_values)


def check_comeback(scores: dict, user_id: str, puzzle_num: str) -> str | None:
    """Check if the player bounced back from a bad previous score."""
    all_puzzles = sorted(scores.keys(), key=lambda x: int(x.replace(",", "")))
    if puzzle_num not in all_puzzles:
        return None
    puzzle_idx = all_puzzles.index(puzzle_num)
    if puzzle_idx < 1:
        return None

    prev_puzzle = all_puzzles[puzzle_idx - 1]
    if user_id not in scores[prev_puzzle]:
        return None

    prev_str = scores[prev_puzzle][user_id]["score"]
    curr_str = scores[puzzle_num][user_id]["score"]
    prev = 7 if prev_str == "X" else int(prev_str)
    curr = 7 if curr_str == "X" else int(curr_str)

    if prev >= 6 and curr <= 3:
        templates = COMMENTARY.get("comeback_strong", [])
        if templates:
            return "📈 " + random.choice(templates).format(prev_score=prev_str, score=curr_str)
        return f"📈 comeback! {prev_str}/6 → {curr_str}/6"
    if prev >= 5 and curr < prev:
        templates = COMMENTARY.get("comeback_ok", [])
        if templates:
            return "📈 " + random.choice(templates).format(prev_score=prev_str, score=curr_str)
    return None


def check_personal_best(scores: dict, user_id: str) -> str | None:
    """Check if the latest score is the player's best in the last 30 games."""
    user_scores, _ = get_user_scores(scores, user_id)
    if len(user_scores) < 10:
        return None

    current = user_scores[-1]
    if current >= 7:
        return None

    recent = user_scores[-31:-1]
    if not recent:
        return None

    if current < min(recent):
        templates = COMMENTARY.get("personal_best", [])
        if templates:
            return "🏅 " + random.choice(templates).format(games=len(recent))
        return f"🏅 best score in {len(recent)} games!"
    return None


def get_smart_commentary(scores: dict, user_id: str, puzzle_num: str, score: str, hard_mode: bool) -> list[str]:
    """Build context-aware commentary for a score. Returns prioritized reply list."""
    replies = []
    score_val = 7 if score == "X" else int(score)

    # Base score commentary (always)
    base = get_commentary(score)
    if base:
        replies.append(base)

    # Collect contextual commentary (limit to avoid spam)
    context = []

    # Hard mode
    if hard_mode:
        if score == "X":
            key = "hard_mode_fail"
        elif score_val <= 4:
            key = "hard_mode_good"
        else:
            key = "hard_mode_survive"
        templates = COMMENTARY.get(key, [])
        if templates:
            context.append(random.choice(templates))

    # Streak
    streak_msg = check_streak(scores, user_id)
    if streak_msg:
        context.append(streak_msg)

    # Close call on streak (6/6 while on a streak)
    if score_val == 6:
        _, puzzles = get_user_scores(scores, user_id)
        current_streak, _ = calc_streak(puzzles)
        if current_streak >= 3:
            templates = COMMENTARY.get("close_call_on_streak", [])
            if templates:
                context.append(random.choice(templates).format(streak=current_streak))

    # Comeback
    comeback = check_comeback(scores, user_id, puzzle_num)
    if comeback:
        context.append(comeback)

    # Hot/cold
    hot_cold = check_hot_cold(scores, user_id)
    if hot_cold:
        context.append(hot_cold)

    # Personal best
    pb = check_personal_best(scores, user_id)
    if pb:
        context.append(pb)

    # Pick up to 2 contextual replies to avoid spam
    if len(context) > 2:
        context = random.sample(context, 2)
    replies.extend(context)

    return replies


def check_group_records(scores: dict) -> str | None:
    """Check if the latest puzzle set a group record for best/worst average."""
    puzzle_avgs = []
    for puzzle_num, players in scores.items():
        vals = [7 if d["score"] == "X" else int(d["score"]) for d in players.values()]
        if len(vals) >= 2:
            puzzle_avgs.append((puzzle_num, sum(vals) / len(vals)))

    if len(puzzle_avgs) < 5:
        return None

    latest = max(scores.keys(), key=lambda x: int(x.replace(",", "")))
    latest_entry = next((p for p in puzzle_avgs if p[0] == latest), None)
    if not latest_entry:
        return None

    _, latest_avg = latest_entry
    all_avgs = [avg for _, avg in puzzle_avgs]

    if latest_avg <= min(all_avgs) and all_avgs.count(latest_avg) == 1:
        return f"🏆 *New group record!* Best group average ever — *{latest_avg:.1f}*"
    if latest_avg >= max(all_avgs) and all_avgs.count(latest_avg) == 1:
        return "📉 *New group record...* worst group average ever. we don't talk about this one."

    return None


def get_group_streak(scores: dict) -> int:
    """Count consecutive recent puzzles where all active players participated."""
    active = get_active_players(scores)
    if not active:
        return 0

    all_puzzles = sorted(scores.keys(), key=lambda x: int(x.replace(",", "")), reverse=True)
    streak = 0
    for puzzle in all_puzzles:
        if active <= set(scores[puzzle].keys()):
            streak += 1
        else:
            break
    return streak


def check_puzzle_milestone(puzzle_num: str) -> str | None:
    """Check if this puzzle number is a milestone worth celebrating."""
    num = int(puzzle_num.replace(",", ""))
    if num % 500 == 0:
        return f"🎊 *Puzzle {num}!* A major Wordle milestone!"
    if num % 100 == 0:
        return f"🎯 *Puzzle {num}!* Another century of Wordles."
    return None


WORDLE_LAUNCH = date(2021, 6, 19)


def _puzzle_range_for_month(year: int, month: int) -> tuple[int, int]:
    """Return (start_puzzle, end_puzzle) for a given month."""
    _, last_day = calendar.monthrange(year, month)
    start = (date(year, month, 1) - WORDLE_LAUNCH).days
    end = (date(year, month, last_day) - WORDLE_LAUNCH).days
    return start, end


def _filter_scores_by_puzzle_range(scores: dict, start: int, end: int) -> dict:
    """Filter scores dict to only include puzzles in the given range."""
    return {
        p: players for p, players in scores.items()
        if start <= int(p.replace(",", "")) <= end
    }


def _build_period_standings(player_stats: dict) -> tuple[list[str], list[tuple]]:
    """Build ranked standings lines from player stats. Returns (lines, ranked)."""
    ranked = sorted(player_stats.items(), key=lambda x: sum(x[1]) / len(x[1]))
    lines = []
    prev_avg = None
    current_rank = 0
    for i, (uid, scores_list) in enumerate(ranked):
        avg = sum(scores_list) / len(scores_list)
        rounded = round(avg, 1)
        if rounded != prev_avg:
            current_rank = i
            prev_avg = rounded
        games = len(scores_list)
        fails = scores_list.count(7)
        lines.append(
            f"  {rank_icon(current_rank)} <@{uid}> — avg *{avg:.1f}* "
            f"({games} games{f', {fails} fails' if fails else ''})"
        )
    return lines, ranked


def build_monthly_recap(scores: dict, year: int, month: int) -> str | None:
    """Build a recap for a specific month."""
    start, end = _puzzle_range_for_month(year, month)
    month_scores = _filter_scores_by_puzzle_range(scores, start, end)
    if not month_scores:
        return None

    player_stats: dict[str, list[int]] = {}
    for players in month_scores.values():
        for uid, data in players.items():
            if uid not in player_stats:
                player_stats[uid] = []
            s = data["score"]
            player_stats[uid].append(7 if s == "X" else int(s))

    if not player_stats:
        return None

    month_name = calendar.month_name[month]
    lines = [f"📅 *{month_name} {year} Recap*\n"]

    standings, ranked = _build_period_standings(player_stats)

    # Champion
    champ_id, champ_scores = ranked[0]
    champ_avg = sum(champ_scores) / len(champ_scores)
    lines.append(f"👑 *Champion:* <@{champ_id}> — avg *{champ_avg:.1f}* over {len(champ_scores)} games\n")
    lines.append("*Standings:*")
    lines.extend(standings)
    lines.append("")

    # Best single solve
    best_score = 8
    best_uid = best_puzzle = None
    for puzzle_num, players in month_scores.items():
        for uid, data in players.items():
            val = 7 if data["score"] == "X" else int(data["score"])
            if val < best_score:
                best_score, best_uid, best_puzzle = val, uid, puzzle_num
    if best_uid and best_score < 7:
        lines.append(f"⚡ *Best solve:* <@{best_uid}> — {best_score}/6 on puzzle {best_puzzle}")

    # Most X's
    most_fails_uid = max(player_stats, key=lambda uid: player_stats[uid].count(7))
    fails = player_stats[most_fails_uid].count(7)
    if fails > 0:
        lines.append(f"💀 *Most X's:* <@{most_fails_uid}> — {fails}")

    # Group stats
    all_scores = [s for sl in player_stats.values() for s in sl]
    group_avg = sum(all_scores) / len(all_scores)
    lines.append(f"\n📊 *Group average:* *{group_avg:.1f}* across {len(month_scores)} puzzles")

    return "\n".join(lines)


def build_yearly_recap(scores: dict, year: int) -> str | None:
    """Build a year-end recap with superlatives."""
    start = (date(year, 1, 1) - WORDLE_LAUNCH).days
    end = (date(year, 12, 31) - WORDLE_LAUNCH).days
    year_scores = _filter_scores_by_puzzle_range(scores, start, end)
    if not year_scores:
        return None

    player_stats: dict[str, list[int]] = {}
    for players in year_scores.values():
        for uid, data in players.items():
            if uid not in player_stats:
                player_stats[uid] = []
            s = data["score"]
            player_stats[uid].append(7 if s == "X" else int(s))

    if not player_stats:
        return None

    lines = [f"🎆 *{year} Wordle Year in Review*\n"]
    standings, ranked = _build_period_standings(player_stats)

    champ_id, champ_scores = ranked[0]
    champ_avg = sum(champ_scores) / len(champ_scores)
    lines.append(f"👑 *Player of the Year:* <@{champ_id}> — avg *{champ_avg:.1f}* over {len(champ_scores)} games\n")
    lines.append("*Final Standings:*")
    lines.extend(standings)
    lines.append("")

    # Most consistent (lowest std dev, min 10 games)
    consistency = []
    for uid, sl in player_stats.items():
        if len(sl) >= 10:
            avg = sum(sl) / len(sl)
            std = (sum((s - avg) ** 2 for s in sl) / len(sl)) ** 0.5
            consistency.append((uid, std))
    if consistency:
        most_consistent = min(consistency, key=lambda x: x[1])
        lines.append(f"🎯 *Most consistent:* <@{most_consistent[0]}>")

    # Most dedicated
    most_games_uid = max(player_stats, key=lambda uid: len(player_stats[uid]))
    lines.append(f"📈 *Most dedicated:* <@{most_games_uid}> — {len(player_stats[most_games_uid])} games")

    # Best single solve
    best_score = 8
    best_uid = best_puzzle = None
    for puzzle_num, players in year_scores.items():
        for uid, data in players.items():
            val = 7 if data["score"] == "X" else int(data["score"])
            if val < best_score:
                best_score, best_uid, best_puzzle = val, uid, puzzle_num
    if best_uid and best_score < 7:
        lines.append(f"⚡ *Best solve:* <@{best_uid}> — {best_score}/6 on puzzle {best_puzzle}")

    # Most X's survived
    most_fails_uid = max(player_stats, key=lambda uid: player_stats[uid].count(7))
    fails = player_stats[most_fails_uid].count(7)
    if fails > 0:
        lines.append(f"💀 *Survived the most X's:* <@{most_fails_uid}> — {fails}")

    # Group stats
    all_scores = [s for sl in player_stats.values() for s in sl]
    group_avg = sum(all_scores) / len(all_scores)
    lines.append(f"\n📊 *Group average:* *{group_avg:.1f}* across {len(year_scores)} puzzles")
    lines.append(f"🧑‍🤝‍🧑 *Active players:* {len(player_stats)}")

    return "\n".join(lines)


def backfill_channel(channel_id: str) -> int:
    count = 0
    cursor = None
    while True:
        kwargs = {"channel": channel_id, "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        resp = app.client.conversations_history(**kwargs)
        for msg in resp.get("messages", []):
            text = msg.get("text", "")
            match = WORDLE_RE.search(text)
            if match and "user" in msg:
                puzzle_num = match.group(1).replace(",", "")
                score = match.group(2)
                hard_mode = bool(HARD_MODE_RE.search(text))
                result = record_score(msg["user"], puzzle_num, score, hard_mode)
                if result is not None:
                    count += 1
        meta = resp.get("response_metadata", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break
    logging.info(f"Backfill complete: {count} new scores from {channel_id}")
    return count


# --- Scheduled tasks ---

def post_all_played_summary(channel_id: str, scores: dict):
    """Post daily summary and leaderboard when all active players have played."""
    latest = max(scores.keys(), key=lambda x: int(x.replace(",", "")))

    # Check if we already posted for this puzzle
    config = load_config()
    if config.get("last_all_played_puzzle") == latest:
        return

    config["last_all_played_puzzle"] = latest
    save_config(config)

    templates = COMMENTARY.get("all_played", ["Everyone's in! Let's see how you all did."])
    app.client.chat_postMessage(
        channel=channel_id,
        text=random.choice(templates) + "\n",
    )

    summary = build_daily_summary(scores)
    if summary:
        app.client.chat_postMessage(channel=channel_id, text=summary)

    # Group records
    record = check_group_records(scores)
    if record:
        app.client.chat_postMessage(channel=channel_id, text=record)

    lb = build_leaderboard(scores, days=7)
    app.client.chat_postMessage(channel=channel_id, text=lb)

    # Group streak
    group_streak = get_group_streak(scores)
    if group_streak >= 3 and group_streak % 5 == 0:
        app.client.chat_postMessage(
            channel=channel_id,
            text=f"🤝 *{group_streak}-day group streak!* Everyone's been showing up. Don't be the one to break it.",
        )
    elif group_streak >= 3:
        app.client.chat_postMessage(
            channel=channel_id,
            text=f"🤝 group streak: *{group_streak} days* and counting.",
        )


def schedule_daily_tasks():
    """Run daily tasks: morning nudge at 8am, summary at 7pm, weekly champion Sunday."""
    import time as _time

    while True:
        now = datetime.now()

        # Next event: 8am nudge or 7pm summary
        morning = now.replace(hour=8, minute=0, second=0, microsecond=0)
        evening = now.replace(hour=19, minute=0, second=0, microsecond=0)

        targets = []
        if now < morning:
            targets.append(("morning", morning))
        if now < evening:
            targets.append(("evening", evening))
        if not targets:
            # Both passed today, schedule morning tomorrow
            targets.append(("morning", morning + timedelta(days=1)))

        event_type, target = targets[0]
        wait_secs = (target - now).total_seconds()
        logging.info(f"Next scheduled event: {event_type} in {wait_secs / 3600:.1f} hours")
        _time.sleep(wait_secs)

        config = load_config()
        channel_id = config.get("wordle_channel")
        if not channel_id:
            continue

        scores = load_scores()
        now = datetime.now()

        if event_type == "morning":
            nudges = COMMENTARY.get("morning_nudges", ["time to wordle."])
            nudge = random.choice(nudges)
            yesterday = (now - timedelta(days=1)).date()
            answer = fetch_wordle_answer(yesterday)
            if answer:
                nudge = f"yesterday's answer was *{answer.upper()}*. {nudge}"
            app.client.chat_postMessage(
                channel=channel_id,
                text=nudge,
            )

        elif event_type == "evening":
            # Skip daily summary + shame if already posted via all-played trigger
            latest = max(scores.keys(), key=lambda x: int(x.replace(",", ""))) if scores else None
            already_posted = latest and config.get("last_all_played_puzzle") == latest

            if not already_posted:
                # Daily summary
                summary = build_daily_summary(scores)
                if summary:
                    app.client.chat_postMessage(channel=channel_id, text=summary)

                # Shame list
                shame = build_shame_list(scores)
                if "Everyone" not in shame:
                    app.client.chat_postMessage(channel=channel_id, text=shame)

            # Rivalry check
            rivalry = check_rivalry(scores)
            if rivalry:
                app.client.chat_postMessage(channel=channel_id, text=rivalry)

            # Weekly champion on Sunday night
            if now.weekday() == 6:
                lb = build_leaderboard(scores, days=7)
                app.client.chat_postMessage(
                    channel=channel_id,
                    text=f"📣 *Weekly Wordle Champion*\n\n{lb}",
                )

            # Monthly recap on the last day of the month
            _, last_day = calendar.monthrange(now.year, now.month)
            if now.day == last_day:
                recap = build_monthly_recap(scores, now.year, now.month)
                if recap:
                    app.client.chat_postMessage(channel=channel_id, text=recap)

            # Yearly recap on Dec 31
            if now.month == 12 and now.day == 31:
                yearly = build_yearly_recap(scores, now.year)
                if yearly:
                    app.client.chat_postMessage(channel=channel_id, text=yearly)


# --- Event handlers ---

@app.message(WORDLE_RE)
def handle_wordle_score(message, say, context):
    text = message.get("text", "")
    match = WORDLE_RE.search(text)
    if not match:
        return

    puzzle_num = match.group(1).replace(",", "")
    score = match.group(2)
    hard_mode = bool(HARD_MODE_RE.search(text))
    user_id = message["user"]

    result = record_score(user_id, puzzle_num, score, hard_mode)
    if result is None:
        return

    # Save channel for scheduled posts
    config = load_config()
    if not config.get("wordle_channel"):
        config["wordle_channel"] = message["channel"]
        save_config(config)

    # React
    try:
        reaction = {
            "1": "exploding_head",
            "2": "fire",
            "3": "ok_hand",
            "4": "thumbsup",
            "5": "sweat_smile",
            "6": "relieved",
            "X": "skull",
        }.get(score, "eyes")

        app.client.reactions_add(
            channel=message["channel"],
            timestamp=message["ts"],
            name=reaction,
        )

        if hard_mode:
            app.client.reactions_add(
                channel=message["channel"],
                timestamp=message["ts"],
                name="star",
            )
    except Exception as e:
        logging.warning(f"Could not add reaction: {e}")

    # Thread replies: context-aware commentary + achievements
    scores = load_scores()
    replies = get_smart_commentary(scores, user_id, puzzle_num, score, hard_mode)

    milestone_msg = check_milestone(scores, user_id)
    if milestone_msg:
        replies.append(milestone_msg)

    achievements = check_achievements(scores, user_id)
    replies.extend(achievements)

    for reply in replies:
        say(text=reply, thread_ts=message["ts"])

    # Puzzle number milestones (post to channel, not thread)
    puzzle_milestone = check_puzzle_milestone(puzzle_num)
    if puzzle_milestone:
        config = load_config()
        if config.get("last_puzzle_milestone") != puzzle_num:
            config["last_puzzle_milestone"] = puzzle_num
            save_config(config)
            say(text=puzzle_milestone)

    # Check if all active players have now played — post summary immediately
    active = get_active_players(scores)
    latest = max(scores.keys(), key=lambda x: int(x.replace(",", "")))
    today_players = set(scores[latest].keys())
    if active and active <= today_players:
        post_all_played_summary(message["channel"], scores)


@app.command("/wordle")
def handle_wordle_command(ack, respond, say, command):
    ack()
    args = command.get("text", "").strip()
    args_lower = args.lower()
    scores = load_scores()

    # --- Public (visible to channel) ---
    if args_lower in ("", "leaderboard", "lb"):
        say(text=build_leaderboard(scores, days=7))

    elif args_lower == "monthly":
        say(text=build_leaderboard(scores, days=30))

    elif args_lower in ("today", "daily"):
        summary = build_daily_summary(scores)
        say(text=summary or "No scores for today's puzzle yet!")

    elif args_lower == "alltime":
        say(text=build_leaderboard(scores, days=9999))

    elif args_lower == "shame":
        say(text=build_shame_list(scores))

    # --- Ephemeral (only visible to requester) ---
    elif args_lower in ("me", "stats", "mystats"):
        respond(text=build_personal_stats(scores, command["user_id"]))

    elif args_lower.startswith("vs"):
        mention_match = re.search(r"<@(\w+)(?:\|[^>]*)?>", args)
        if mention_match:
            other_user = mention_match.group(1)
        else:
            # Slack may not escape mentions in slash commands — look up by name
            name = re.sub(r"^vs\s+@?", "", args, flags=re.IGNORECASE).strip()
            other_user = lookup_user_by_name(name) if name else None

        if other_user:
            respond(text=build_vs(scores, command["user_id"], other_user))
        else:
            respond(text="Usage: `/wordle vs @someone`")

    elif args_lower in ("hardest", "puzzles"):
        respond(text=build_hardest_puzzles(scores))

    elif args_lower == "achievements":
        config = load_config()
        earned = config.get("achievements", {}).get(command["user_id"], [])
        if earned:
            lines = ["*Your Achievements*\n"]
            for key in earned:
                if key in ACHIEVEMENTS:
                    emoji, desc = ACHIEVEMENTS[key]
                    lines.append(f"  {emoji} — {desc}")
            respond(text="\n".join(lines))
        else:
            respond(text="No achievements yet — keep playing!")

    elif args_lower.startswith("backfill"):
        channel_id = command["channel_id"]
        respond(text="Scanning channel history for Wordle scores...")
        count = backfill_channel(channel_id)
        # Recalculate achievements for all players
        scores = load_scores()
        all_users = set()
        for puzzle in scores.values():
            all_users.update(puzzle.keys())
        for uid in all_users:
            check_achievements(scores, uid)
        respond(text=f"Backfill complete! Found {count} new scores. Achievements recalculated for {len(all_users)} players.")

    elif args_lower == "invite":
        say(text=(
            "👋 *Hey everyone!* I'm the Wordle bot for this channel.\n\n"
            "Here's how it works: play the daily Wordle at https://www.nytimes.com/games/wordle/ "
            "and paste your share result here. I'll track your scores, keep a leaderboard, "
            "and talk a little trash along the way.\n\n"
            "*What to expect:*\n"
            "• 📊 Leaderboards, streaks, and head-to-head rivalries\n"
            "• 🏆 Achievements and milestones as you play\n"
            "• 🎉 As soon as all active players have posted, I'll drop the daily results and leaderboard — no waiting around\n"
            "• 👀 A gentle nudge if you forget\n\n"
            "You're considered an \"active player\" once you post your first score, "
            "and you stay active as long as you've played at least once in the last 14 puzzles.\n\n"
            "Type `/wordle help` to see all commands. Now get in here!"
        ))

    elif args_lower == "help":
        respond(text=(
            "*Wordle Bot Commands*\n\n"
            "*📢 Public (visible to channel):*\n"
            "• `/wordle` — leaderboard (last 7 days)\n"
            "• `/wordle monthly` — last 30 days\n"
            "• `/wordle alltime` — all time\n"
            "• `/wordle today` — today's puzzle results\n"
            "• `/wordle shame` — who hasn't played today\n"
            "• `/wordle invite` — introduce the bot to the channel\n\n"
            "*🔒 Private (only you):*\n"
            "• `/wordle me` — your personal stats & badges\n"
            "• `/wordle vs @someone` — head-to-head comparison\n"
            "• `/wordle achievements` — your earned badges\n"
            "• `/wordle hardest` — hardest & easiest puzzles\n"
            "• `/wordle backfill` — scan channel history\n"
            "• `/wordle help` — this message\n\n"
            "Just paste your Wordle share and I'll track it!"
        ))

    else:
        respond(text="Unknown command. Try `/wordle help`")


if __name__ == "__main__":
    logging.info("Starting Wordle bot...")

    summary_thread = threading.Thread(target=schedule_daily_tasks, daemon=True)
    summary_thread.start()

    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()
