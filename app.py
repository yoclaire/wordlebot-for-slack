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
import threading
from datetime import datetime, timedelta
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

ROASTS = [
    "oof. at least you tried.",
    "the word fought back today, huh?",
    "we don't talk about this one.",
    "technically still a win... technically.",
    "the important thing is you had fun. right?",
    "F in the chat.",
    "have you considered connections instead?",
]

CELEBRATIONS = {
    "1": [
        "WHAT. first try?! are you cheating?",
        "literally impossible. we're calling the authorities.",
        "one guess. ONE. explain yourself.",
    ],
    "2": [
        "two?! disgusting talent.",
        "ok show-off, we see you.",
        "casual two. no big deal. (it's a big deal.)",
    ],
    "3": [
        "clean solve.",
        "smooth. very smooth.",
        "chef's kiss.",
    ],
}

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

SHAME_MESSAGES = [
    "still waiting on {names} to post today... 👀",
    "hey {names} — the wordle isn't going to solve itself",
    "{names}: we're not mad, just disappointed",
    "the clock is ticking, {names}",
]

MORNING_NUDGES = [
    "☕ new wordle just dropped. you know what to do.",
    "🌅 rise and wordle.",
    "📰 today's wordle is live. no spoilers.",
    "good morning! the wordle awaits: https://www.nytimes.com/games/wordle/",
]


# --- Data helpers ---


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
    if score == "X":
        return random.choice(ROASTS)
    if score in CELEBRATIONS:
        return random.choice(CELEBRATIONS[score])
    return None


def check_milestone(scores: dict, user_id: str) -> str | None:
    count = sum(1 for p in scores.values() if user_id in p)
    if count in MILESTONES:
        return f"🎉 <@{user_id}> just logged Wordle #{count}!"
    return None


def check_streak(scores: dict, user_id: str) -> str | None:
    _, puzzles = get_user_scores(scores, user_id)
    current, _ = calc_streak(puzzles)
    if current >= 7 and current % 7 == 0:
        return f"🔥 <@{user_id}> is on a *{current}-day streak*!"
    if current == 3:
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
        return f"📈 <@{user_id}> is on a hot streak — *{recent_avg:.1f}* avg over last 5 vs *{overall_avg:.1f}* overall"
    if diff <= -1.0:
        return f"📉 <@{user_id}> going through it — *{recent_avg:.1f}* avg over last 5 vs *{overall_avg:.1f}* overall"
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
    for i, (user_id, scores_list) in enumerate(ranked):
        avg = sum(scores_list) / len(scores_list)
        games = len(scores_list)
        best = min(scores_list)
        fails = scores_list.count(7)
        best_str = "X" if best == 7 else str(best)
        lines.append(
            f"{rank_icon(i)} <@{user_id}> — avg *{avg:.1f}* "
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
        key=lambda x: (7 if x[1]["score"] == "X" else int(x[1]["score"])),
    )

    lines = [f"*Wordle {latest} Results*\n"]
    for i, (user_id, data) in enumerate(ranked):
        hm = " ⭐" if data.get("hard_mode") else ""
        lines.append(f"{rank_icon(i)} <@{user_id}> — {data['score']}/6{hm}")

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

    # Recent form
    recent = stats["recent_5"]
    if len(recent) >= 5:
        recent_avg = sum(recent) / len(recent)
        trend = "📈" if recent_avg < stats["avg"] else "📉" if recent_avg > stats["avg"] else "➡️"
        form_str = f"\n{trend} Recent form (last 5): *{recent_avg:.1f}* avg"
    else:
        form_str = ""

    return (
        f"*Your Wordle Stats*\n\n"
        f"Games: *{stats['games']}* | "
        f"Avg: *{stats['avg']:.1f}* | "
        f"Best: *{stats['best'] if stats['best'] < 7 else 'X'}* | "
        f"Worst: *{stats['worst'] if stats['worst'] < 7 else 'X'}*\n"
        f"Win rate: *{stats['wins'] / stats['games'] * 100:.0f}%* | "
        f"Current streak: *{stats['current_streak']}* | "
        f"Best streak: *{stats['best_streak']}*"
        f"{hm_str}{form_str}{achievement_str}\n"
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
    return random.choice(SHAME_MESSAGES).format(names=names)


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

    app.client.chat_postMessage(
        channel=channel_id,
        text="Everyone's in! 🎉 Let's see how you all did.\n",
    )

    summary = build_daily_summary(scores)
    if summary:
        app.client.chat_postMessage(channel=channel_id, text=summary)

    lb = build_leaderboard(scores, days=7)
    app.client.chat_postMessage(channel=channel_id, text=lb)


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
            app.client.chat_postMessage(
                channel=channel_id,
                text=random.choice(MORNING_NUDGES),
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

    # Thread replies
    replies = []

    commentary = get_commentary(score)
    if commentary:
        replies.append(commentary)

    if hard_mode and score != "X":
        replies.append("⭐ hard mode. respect.")

    scores = load_scores()

    streak_msg = check_streak(scores, user_id)
    if streak_msg:
        replies.append(streak_msg)

    milestone_msg = check_milestone(scores, user_id)
    if milestone_msg:
        replies.append(milestone_msg)

    hot_cold = check_hot_cold(scores, user_id)
    if hot_cold:
        replies.append(hot_cold)

    achievements = check_achievements(scores, user_id)
    replies.extend(achievements)

    for reply in replies:
        say(text=reply, thread_ts=message["ts"])

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
