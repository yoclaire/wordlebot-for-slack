"""
Wordle score tracker for Slack.

Watches a channel for Wordle share pastes, parses scores,
tracks stats, posts leaderboards, and talks trash.

Slack wiring lives here; the testable core lives in logic.py.
"""

import os
import re
import random
import signal
import logging
import calendar
import threading
from datetime import datetime, timedelta

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from logic import (
    ACHIEVEMENTS,
    COMMENTARY,
    HARD_MODE_RE,
    SUPPLEMENTAL,
    WORDLE_RE,
    _apply_diacritics,
    _fetch_marine_conditions,
    _moon_phase,
    activate_alt_mode,
    alt_mode_active,
    build_daily_summary,
    build_hardest_puzzles,
    build_leaderboard,
    build_monthly_recap,
    build_personal_stats,
    build_shame_list,
    build_vs,
    build_yearly_recap,
    check_achievements,
    check_group_records,
    check_milestone,
    check_puzzle_milestone,
    check_rivalry,
    fetch_wordle_answer,
    get_active_players,
    get_group_streak,
    get_smart_commentary,
    load_config,
    load_scores,
    lookup_user_by_name,
    record_score,
    record_scores_bulk,
    update_config,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = App(token=os.environ["SLACK_BOT_TOKEN"])

_self_id = None


def backfill_channel(channel_id: str) -> int:
    entries = []
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
                entries.append((
                    msg["user"],
                    match.group(1).replace(",", ""),
                    match.group(2),
                    bool(HARD_MODE_RE.search(text)),
                ))
        meta = resp.get("response_metadata", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break
    count = record_scores_bulk(entries)
    logging.info(f"Backfill complete: {count} new scores from {channel_id}")
    return count


# --- Scheduled tasks ---

def post_all_played_summary(channel_id: str, scores: dict):
    """Post daily summary and leaderboard when all active players have played."""
    latest = max(scores.keys(), key=lambda x: int(x.replace(",", "")))

    # Claim this puzzle atomically so two concurrent handlers can't both
    # decide "all played" and double-post the summary.
    def _claim(config):
        if config.get("last_all_played_puzzle") == latest:
            return False
        config["last_all_played_puzzle"] = latest
        return True

    if not update_config(_claim):
        return

    source = SUPPLEMENTAL if alt_mode_active() and "all_played" in SUPPLEMENTAL else COMMENTARY
    templates = source.get("all_played", ["Everyone's in! Let's see how you all did."])
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
        if alt_mode_active() and "group_streak_major" in SUPPLEMENTAL:
            text = random.choice(SUPPLEMENTAL["group_streak_major"]).format(streak=group_streak)
        else:
            text = f"🤝 *{group_streak}-day group streak!* Everyone's been showing up. Don't be the one to break it."
        app.client.chat_postMessage(channel=channel_id, text=text)
    elif group_streak >= 3:
        if alt_mode_active() and "group_streak" in SUPPLEMENTAL:
            text = random.choice(SUPPLEMENTAL["group_streak"]).format(streak=group_streak)
        else:
            text = f"🤝 group streak: *{group_streak} days* and counting."
        app.client.chat_postMessage(channel=channel_id, text=text)


def schedule_daily_tasks():
    """Run daily tasks: morning nudge at 8am, summary at 10pm, weekly champion Sunday."""
    import time as _time

    while True:
        try:
            now = datetime.now()

            # Next event: 8am nudge or 10pm summary
            morning = now.replace(hour=8, minute=0, second=0, microsecond=0)
            evening = now.replace(hour=22, minute=0, second=0, microsecond=0)

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
                if alt_mode_active():
                    parts = []
                    conditions = _fetch_marine_conditions()
                    if conditions:
                        parts.append(conditions)
                    briefings = SUPPLEMENTAL.get("morning_briefing", [])
                    if briefings:
                        parts.append(random.choice(briefings))
                    moon = SUPPLEMENTAL.get("moon_phase", {}).get(_moon_phase(now), [])
                    if moon:
                        parts.append(random.choice(moon))
                    yesterday = (now - timedelta(days=1)).date()
                    answer = fetch_wordle_answer(yesterday)
                    if answer:
                        parts.append(f"Oh. Yesterday's answer was *{answer.upper()}*.")
                    if parts:
                        app.client.chat_postMessage(
                            channel=channel_id,
                            text="\n\n".join(parts),
                        )
                else:
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

                    if alt_mode_active():
                        parts = []
                        conditions = _fetch_marine_conditions()
                        if conditions:
                            parts.append(conditions)
                        briefings = SUPPLEMENTAL.get("evening_briefing", [])
                        if briefings:
                            parts.append(random.choice(briefings))
                        moon = SUPPLEMENTAL.get("moon_phase", {}).get(_moon_phase(now), [])
                        if moon:
                            parts.append(random.choice(moon))
                        if parts:
                            app.client.chat_postMessage(
                                channel=channel_id,
                                text="\n\n".join(parts),
                            )

                    # Shame list
                    shame, has_missing = build_shame_list(scores)
                    if has_missing:
                        app.client.chat_postMessage(channel=channel_id, text=shame)

                # Rivalry check
                rivalry = check_rivalry(scores)
                if rivalry:
                    app.client.chat_postMessage(channel=channel_id, text=rivalry)

                # Weekly champion on Sunday night
                if now.weekday() == 6:
                    lb = build_leaderboard(scores, days=7)
                    if alt_mode_active():
                        intros = SUPPLEMENTAL.get("weekly_intro", [])
                        header = random.choice(intros) if intros else "Weekly results"
                        app.client.chat_postMessage(
                            channel=channel_id,
                            text=f"{header}\n\n{lb}",
                        )
                    else:
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
        except Exception:
            logging.exception("Scheduler error, will retry next cycle")
            _time.sleep(60)


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
    def _set_channel(config):
        if config.get("wordle_channel"):
            return False
        config["wordle_channel"] = message["channel"]
        return True

    update_config(_set_channel)

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

        override = SUPPLEMENTAL.get("reaction_override", "")
        if alt_mode_active() and override:
            reaction = override

        app.client.reactions_add(
            channel=message["channel"],
            timestamp=message["ts"],
            name=reaction,
        )

        if hard_mode and not (alt_mode_active() and override):
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
        def _claim_milestone(config):
            if config.get("last_puzzle_milestone") == puzzle_num:
                return False
            config["last_puzzle_milestone"] = puzzle_num
            return True

        if update_config(_claim_milestone):
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
        shame, _ = build_shame_list(scores)
        say(text=shame)

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
            other_user = lookup_user_by_name(app.client, name) if name else None

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


@app.event("reaction_added")
def _handle_reaction_event(event, say):
    if _self_id is None:
        return
    if event.get("item_user") != _self_id:
        return
    trigger = SUPPLEMENTAL.get("trigger_reaction", "")
    if not trigger or event.get("reaction") != trigger:
        return
    channel = event.get("item", {}).get("channel")
    if not activate_alt_mode(channel):
        return
    if not channel:
        return

    emoji = SUPPLEMENTAL.get("reaction_override", trigger)
    activations = SUPPLEMENTAL.get("mode_on", [])
    label = _apply_diacritics(random.choice(activations) if activations else "")
    app.client.chat_postMessage(channel=channel, text=f":{emoji}: {label} :{emoji}:")


if __name__ == "__main__":
    logging.info("Starting Wordle bot...")

    try:
        _self_id = app.client.auth_test()["user_id"]
        logging.info(f"Bot user ID: {_self_id}")
    except Exception as e:
        logging.warning(f"Could not retrieve bot user ID: {e}")

    summary_thread = threading.Thread(target=schedule_daily_tasks, daemon=True)
    summary_thread.start()

    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])

    # Graceful shutdown on SIGTERM (docker stop) / SIGINT (Ctrl+C). Without this,
    # handler.start() blocks forever and the container takes the full SIGKILL
    # grace period to exit.
    def _shutdown(signum, _frame):
        logging.info("Received signal %s, shutting down", signum)
        handler.close()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    handler.start()
    logging.info("Bot stopped")
