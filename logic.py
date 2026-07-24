"""
Pure Wordle-tracking logic — parsing, stats, persistence, and message
building. No Slack dependencies, so tests can import this module directly.
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

DATA_DIR = Path("/app/data")
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

SUPPLEMENTAL_FILE = Path(__file__).parent / "supplemental.json"
SUPPLEMENTAL = json.loads(SUPPLEMENTAL_FILE.read_text()) if SUPPLEMENTAL_FILE.exists() else {}

_alt_active = False
_alt_activated_at = None
_alt_channel = None

# Guards the alt-mode globals above. RLock (not Lock) so activate_alt_mode()
# can call alt_mode_active() while already holding it.
_alt_lock = threading.RLock()

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


WORDLE_EPOCH = date(2021, 6, 19)  # Wordle #0


def puzzle_num_to_date(puzzle_num: int | str) -> date:
    """Convert a Wordle puzzle number to its calendar date."""
    return WORDLE_EPOCH + timedelta(days=int(str(puzzle_num).replace(",", "")))


def date_to_puzzle_num(d: date) -> int:
    """Convert a calendar date to its Wordle puzzle number."""
    return (d - WORDLE_EPOCH).days


def current_puzzle_num() -> int:
    """Today's Wordle puzzle number."""
    return date_to_puzzle_num(date.today())


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


_LOCATIONS = {k: tuple(v) for k, v in SUPPLEMENTAL.get("locations", {}).items()}


def _format_ambient(data: dict, loc_name: str) -> str:
    """Format the ambient API response into a short report."""
    current = data.get("current", {})
    wave_h = current.get("wave_height")
    swell_h = current.get("swell_wave_height")
    swell_p = current.get("swell_wave_period")
    swell_d = current.get("swell_wave_direction")
    temp = current.get("sea_surface_temperature")

    if wave_h is None:
        return f"*{loc_name}*: No data available."

    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    compass = dirs[round(swell_d / 22.5) % 16] if swell_d is not None else ""

    if swell_h is not None and swell_p is not None:
        report = (
            f"*{loc_name}*: {swell_h}m swell at {swell_p}s from the {compass}. "
            f"Combined wave height {wave_h}m."
        )
    else:
        report = f"*{loc_name}*: {wave_h}m wave height."

    temp_templates = SUPPLEMENTAL.get("temperature", [])
    if temp is not None and temp_templates:
        report += "\n\n" + random.choice(temp_templates).format(temp=round(temp, 1))
    return report


def _fetch_ambient() -> str | None:
    """Fetch ambient conditions for a random configured location."""
    loc_name = random.choice(list(_LOCATIONS.keys()))
    lat, lon = _LOCATIONS[loc_name]
    url = (
        f"https://marine-api.open-meteo.com/v1/marine?"
        f"latitude={lat}&longitude={lon}"
        f"&current=wave_height,swell_wave_height,swell_wave_period,swell_wave_direction,sea_surface_temperature"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wordlebot"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return _format_ambient(data, loc_name)
    except Exception as e:
        logging.warning(f"Could not fetch ambient conditions: {e}")
        return None


def _cycle_phase(dt: datetime) -> str:
    """Current cycle-phase key (offline, no API)."""
    ref_epoch = datetime(2000, 1, 6, 18, 14)  # cycle reference epoch, UTC
    cycle_days = 29.530588853
    days = (dt - ref_epoch).total_seconds() / 86400.0
    pos = (days % cycle_days) / cycle_days  # 0..1 through the cycle
    idx = int(pos * 8 + 0.5) % 8
    return ["new", "waxing_crescent", "first_quarter", "waxing_gibbous",
            "full", "waning_gibbous", "last_quarter", "waning_crescent"][idx]


def lookup_user_by_name(client, name: str) -> str | None:
    """Look up a Slack user ID by display name, username, or real name."""
    try:
        cursor = None
        while True:
            kwargs = {"limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            resp = client.users_list(**kwargs)
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
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        logging.warning(f"Could not look up user '{name}': {e}")
    return None


def load_scores() -> dict:
    if SCORES_FILE.exists():
        return json.loads(SCORES_FILE.read_text())
    return {}


def save_scores(scores: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(SCORES_FILE) + ".tmp"
    Path(tmp).write_text(json.dumps(scores, indent=2))
    os.replace(tmp, SCORES_FILE)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(config: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(CONFIG_FILE) + ".tmp"
    Path(tmp).write_text(json.dumps(config, indent=2))
    os.replace(tmp, CONFIG_FILE)


# Serializes read-modify-write of config.json — same Bolt thread-pool hazard as
# scores.json. Achievements, the channel id, and milestone flags all RMW config,
# so an unguarded read-mutate-write could silently drop a concurrent update.
_config_lock = threading.Lock()


def update_config(mutate):
    """Atomically read-modify-write config.json under a lock.

    ``mutate(config)`` mutates the loaded config in place and returns a value.
    A falsy return means "nothing changed" and skips the write; a truthy return
    triggers the save. The return value is handed back to the caller, so a
    mutator can both report whether it changed anything and pass data out.
    """
    with _config_lock:
        config = load_config()
        changed = mutate(config)
        if changed:
            save_config(config)
        return changed


# Serializes read-modify-write of scores.json — Bolt dispatches handlers on a
# thread pool, so two pastes can land at once.
_data_lock = threading.Lock()


def record_score(user_id: str, puzzle_num: str, score: str, hard_mode: bool = False) -> str | None:
    """Record a score. Returns the score string or None if already recorded."""
    with _data_lock:
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


def record_scores_bulk(entries: list[tuple[str, str, str, bool]]) -> int:
    """Record many (user_id, puzzle_num, score, hard_mode) entries in one write.

    Skips already-recorded entries. Returns the number of new scores saved.
    """
    with _data_lock:
        scores = load_scores()
        count = 0
        for user_id, puzzle_num, score, hard_mode in entries:
            players = scores.setdefault(puzzle_num, {})
            if user_id not in players:
                players[user_id] = {
                    "score": score,
                    "hard_mode": hard_mode,
                    "timestamp": datetime.now().isoformat(),
                }
                count += 1
        if count:
            save_scores(scores)
        return count


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
    for i in range(1, len(puzzles_played)):
        if puzzles_played[i] - puzzles_played[i - 1] == 1:
            current += 1
        else:
            current = 1
        best = max(best, current)
    return current, best


def get_user_stats(scores: dict, user_id: str, today_puzzle: int | None = None) -> dict | None:
    """Get comprehensive stats for a single user.

    today_puzzle anchors current-streak decay and defaults to today's puzzle;
    a streak is only "current" if the user played today or yesterday.
    """
    user_scores, puzzles_played = get_user_scores(scores, user_id)
    if not user_scores:
        return None

    current_streak, best_streak = calc_streak(puzzles_played)
    if today_puzzle is None:
        today_puzzle = current_puzzle_num()
    if puzzles_played and today_puzzle - puzzles_played[-1] > 1:
        current_streak = 0

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
    source = SUPPLEMENTAL if alt_mode_active() and key in SUPPLEMENTAL else COMMENTARY
    templates = source.get(key, [])
    return random.choice(templates) if templates else None


def _apply_diacritics(text: str) -> str:
    """Add combining diacritical marks to alphabetic characters."""
    _marks = [
        "\u0300", "\u0301", "\u0302", "\u0303", "\u0304", "\u0305",
        "\u0306", "\u0307", "\u0308", "\u030a", "\u030b", "\u030c",
        "\u0327", "\u0328", "\u0330", "\u0331", "\u0332", "\u0333",
    ]
    result = []
    for char in text:
        result.append(char)
        if char.isalpha():
            for _ in range(random.randint(1, 3)):
                result.append(random.choice(_marks))
    return "".join(result)


def _deactivate_alt_mode():
    global _alt_active, _alt_activated_at, _alt_channel
    with _alt_lock:
        _alt_active = False
        _alt_activated_at = None
        _alt_channel = None


ALT_MODE_DURATION = timedelta(hours=24)


def alt_mode_active() -> bool:
    """True while alt mode is on and within its 24h window; expires lazily."""
    with _alt_lock:
        if not _alt_active:
            return False
        if _alt_activated_at is not None and datetime.now() - _alt_activated_at > ALT_MODE_DURATION:
            _deactivate_alt_mode()
            return False
        return True


def activate_alt_mode(channel: str | None) -> bool:
    """Turn alt mode on. Returns False if it was already active."""
    global _alt_active, _alt_activated_at, _alt_channel
    with _alt_lock:
        if alt_mode_active():
            return False
        _alt_active = True
        _alt_activated_at = datetime.now()
        _alt_channel = channel
        return True


def check_milestone(scores: dict, user_id: str) -> str | None:
    count = sum(1 for p in scores.values() if user_id in p)
    if count in MILESTONES:
        if alt_mode_active() and "milestone" in SUPPLEMENTAL:
            return random.choice(SUPPLEMENTAL["milestone"]).format(user_id=user_id, count=count)
        return f"🎉 <@{user_id}> just logged Wordle #{count}!"
    return None


def check_streak(scores: dict, user_id: str) -> str | None:
    _, puzzles = get_user_scores(scores, user_id)
    current, _ = calc_streak(puzzles)
    if current >= 7 and current % 7 == 0:
        key = "streak_epic" if current >= 14 else "streak_hot"
        source = SUPPLEMENTAL if alt_mode_active() and key in SUPPLEMENTAL else COMMENTARY
        templates = source.get(key, [])
        if templates:
            return f"<@{user_id}> — " + random.choice(templates).format(streak=current)
        return f"🔥 <@{user_id}> is on a *{current}-day streak*!"
    if current == 3:
        source = SUPPLEMENTAL if alt_mode_active() and "streak_building" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("streak_building", [])
        if templates:
            return f"<@{user_id}> — " + random.choice(templates).format(streak=current)
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
        source = SUPPLEMENTAL if alt_mode_active() and "hot_hand" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("hot_hand", [])
        if templates:
            return f"<@{user_id}> " + random.choice(templates).format(recent_avg=recent_avg, overall_avg=overall_avg)
        return f"📈 <@{user_id}> is heating up — *{recent_avg:.1f}* avg recently vs *{overall_avg:.1f}* overall"
    if diff <= -1.0:
        source = SUPPLEMENTAL if alt_mode_active() and "cold_spell" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("cold_spell", [])
        if templates:
            return f"<@{user_id}> " + random.choice(templates).format(recent_avg=recent_avg, overall_avg=overall_avg)
        return f"📉 <@{user_id}> going through it — *{recent_avg:.1f}* avg recently vs *{overall_avg:.1f}* overall"
    return None


def check_achievements(scores: dict, user_id: str) -> list[str]:
    """Check for newly earned achievements."""
    stats = get_user_stats(scores, user_id)
    if not stats:
        return []

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

    # Grant + persist atomically so a concurrent handler can't clobber the list.
    def _grant(config):
        earned = config.setdefault("achievements", {}).setdefault(user_id, [])
        new = []
        for key, condition in checks:
            if condition and key not in earned:
                earned.append(key)
                emoji, desc = ACHIEVEMENTS[key]
                new.append(f"{emoji} *Achievement unlocked:* {desc}!")
        return new

    return update_config(_grant) or []


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
            if alt_mode_active() and "rivalry" in SUPPLEMENTAL:
                templates = SUPPLEMENTAL["rivalry"]
                return random.choice(templates).format(uid1=uid1, avg1=avg1, uid2=uid2, avg2=avg2)
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

    if alt_mode_active():
        intros = SUPPLEMENTAL.get("wrap_intro", [])
        header = random.choice(intros) if intros else f"*Puzzle {latest}*"
        lines = [f"{header}\n"]
    else:
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
        if alt_mode_active():
            diff = SUPPLEMENTAL.get("difficulty", {})
            if avg <= 3.0:
                lines.append(f"\n{diff.get('easy', '')}")
            elif avg <= 4.0:
                lines.append(f"\n{diff.get('solid', '')}")
            elif avg <= 5.0:
                lines.append(f"\n{diff.get('tough', '')}")
            else:
                lines.append(f"\n{diff.get('brutal', '')}")
            facts = SUPPLEMENTAL.get("general_facts", [])
            if facts:
                lines.append(f"\n_{random.choice(facts)}_")
        else:
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

    # Fetch answers for all puzzles in one pass
    all_puzzles = {p for p, _, _ in hardest} | {p for p, _, _ in easiest}
    answers = {}
    for puzzle in all_puzzles:
        puzzle_date = puzzle_num_to_date(puzzle)
        answer = fetch_wordle_answer(puzzle_date)
        answers[puzzle] = (puzzle_date, answer)

    def format_line(puzzle, avg, players):
        puzzle_date, answer = answers[puzzle]
        word = f" *{answer.upper()}*" if answer else ""
        return f"  Wordle {puzzle} ({puzzle_date.strftime('%-m/%-d')}{word}) — avg *{avg:.1f}* ({players} players)"

    lines = ["*Hardest Puzzles* 🟥\n"]
    for puzzle, avg, players in hardest:
        lines.append(format_line(puzzle, avg, players))

    lines.append("\n*Easiest Puzzles* 🟩\n")
    for puzzle, avg, players in easiest:
        lines.append(format_line(puzzle, avg, players))

    return "\n".join(lines)


def get_active_players(scores: dict, lookback: int = 14) -> set[str]:
    all_puzzles = sorted(scores.keys(), key=lambda x: int(x.replace(",", "")))
    recent = all_puzzles[-lookback:] if len(all_puzzles) > lookback else all_puzzles
    players = set()
    for puzzle in recent:
        players.update(scores[puzzle].keys())
    return players


def build_shame_list(scores: dict, today_puzzle: int | None = None) -> tuple[str, bool]:
    """Return (message, has_missing) — has_missing is True when players still need to play."""
    if not scores:
        return "No scores recorded yet!", False

    if today_puzzle is None:
        today_puzzle = current_puzzle_num()
    today_players = set(scores.get(str(today_puzzle), {}).keys())
    active = get_active_players(scores)
    missing = active - today_players

    if not missing:
        return "Everyone's played today! 🎉", False

    names = ", ".join(f"<@{uid}>" for uid in missing)
    source = SUPPLEMENTAL if alt_mode_active() and "shame" in SUPPLEMENTAL else COMMENTARY
    templates = source.get("shame", ["{names}: play wordle already"])
    return random.choice(templates).format(names=names), True


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
        source = SUPPLEMENTAL if alt_mode_active() and "comeback_strong" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("comeback_strong", [])
        if templates:
            return random.choice(templates).format(prev_score=prev_str, score=curr_str)
        return f"📈 comeback! {prev_str}/6 → {curr_str}/6"
    if prev >= 5 and curr < prev:
        source = SUPPLEMENTAL if alt_mode_active() and "comeback_ok" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("comeback_ok", [])
        if templates:
            return random.choice(templates).format(prev_score=prev_str, score=curr_str)
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
        source = SUPPLEMENTAL if alt_mode_active() and "personal_best" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("personal_best", [])
        if templates:
            return random.choice(templates).format(games=len(recent))
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
        source = SUPPLEMENTAL if alt_mode_active() and key in SUPPLEMENTAL else COMMENTARY
        templates = source.get(key, [])
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
            source = SUPPLEMENTAL if alt_mode_active() and "close_call_on_streak" in SUPPLEMENTAL else COMMENTARY
            templates = source.get("close_call_on_streak", [])
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
        if alt_mode_active() and "group_record_best" in SUPPLEMENTAL:
            return random.choice(SUPPLEMENTAL["group_record_best"]).format(avg=latest_avg)
        return f"🏆 *New group record!* Best group average ever — *{latest_avg:.1f}*"
    if latest_avg >= max(all_avgs) and all_avgs.count(latest_avg) == 1:
        if alt_mode_active() and "group_record_worst" in SUPPLEMENTAL:
            return random.choice(SUPPLEMENTAL["group_record_worst"])
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
        if alt_mode_active() and "puzzle_milestone_major" in SUPPLEMENTAL:
            return random.choice(SUPPLEMENTAL["puzzle_milestone_major"]).format(num=num)
        return f"🎊 *Puzzle {num}!* A major Wordle milestone!"
    if num % 100 == 0:
        if alt_mode_active() and "puzzle_milestone_century" in SUPPLEMENTAL:
            return random.choice(SUPPLEMENTAL["puzzle_milestone_century"]).format(num=num)
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
    if alt_mode_active():
        intros = SUPPLEMENTAL.get("monthly_intro", [])
        header = random.choice(intros) if intros else f"Monthly report: {month_name} {year}"
        lines = [f"{header}\n"]
    else:
        lines = [f"📅 *{month_name} {year} Recap*\n"]

    standings, ranked = _build_period_standings(player_stats)

    # Champion
    champ_id, champ_scores = ranked[0]
    champ_avg = sum(champ_scores) / len(champ_scores)
    if alt_mode_active():
        lines.append(f"🦀 *Dominant specimen:* <@{champ_id}> — avg *{champ_avg:.1f}* over {len(champ_scores)} foraging sessions\n")
    else:
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

    if alt_mode_active():
        facts = SUPPLEMENTAL.get("general_facts", [])
        if facts:
            lines.append(f"\n_{random.choice(facts)}_")

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

    if alt_mode_active():
        intros = SUPPLEMENTAL.get("yearly_intro", [])
        header = random.choice(intros) if intros else f"Annual report: {year}"
        lines = [f"{header}\n"]
    else:
        lines = [f"🎆 *{year} Wordle Year in Review*\n"]
    standings, ranked = _build_period_standings(player_stats)

    champ_id, champ_scores = ranked[0]
    champ_avg = sum(champ_scores) / len(champ_scores)
    if alt_mode_active():
        lines.append(f"🦀 *Alpha specimen:* <@{champ_id}> — avg *{champ_avg:.1f}* over {len(champ_scores)} sessions\n")
    else:
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

    if alt_mode_active():
        facts = SUPPLEMENTAL.get("general_facts", [])
        if facts:
            lines.append(f"\n_{random.choice(facts)}_")

    return "\n".join(lines)
