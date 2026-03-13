# wordlebot-for-slack

A Slack bot that tracks [Wordle](https://www.nytimes.com/games/wordle/) scores, posts leaderboards, and talks trash.

Just paste your Wordle share into a channel and the bot handles the rest.

## Features

- **Auto-detection** — recognizes Wordle share pastes and reacts with score-appropriate emoji
- **Leaderboards** — weekly, monthly, and all-time rankings by average score
- **Personal stats** — games played, average, distribution histogram, win rate, streaks
- **Head-to-head** — compare yourself against another player
- **Achievements** — unlock badges for milestones (streaks, sub-3 average, hard mode, etc.)
- **Daily summary** — automated 10pm recap of the day's scores with difficulty rating
- **Morning nudge** — optional 8am reminder that a new puzzle is live
- **Shame list** — call out who hasn't played yet today
- **Rivalry alerts** — detects when two players are neck and neck over the last 30 puzzles
- **Hard mode tracking** — recognizes and highlights hard mode solves
- **Backfill** — scan channel history to import past scores

## Slash commands

| Command | Visibility | Description |
|---------|-----------|-------------|
| `/wordle` | Public | Leaderboard (last 7 days) |
| `/wordle monthly` | Public | Last 30 days |
| `/wordle alltime` | Public | All time |
| `/wordle today` | Public | Today's puzzle results |
| `/wordle shame` | Public | Who hasn't played today |
| `/wordle me` | Private | Your personal stats & badges |
| `/wordle vs @someone` | Private | Head-to-head comparison |
| `/wordle achievements` | Private | Your earned badges |
| `/wordle hardest` | Private | Hardest & easiest puzzles |
| `/wordle backfill` | Private | Scan channel history for past scores |
| `/wordle help` | Private | List all commands |

## Setup

### 1. Create a Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** → **From scratch**
2. Name it whatever you like (e.g. "Wordle Bot") and select your workspace

### 2. Configure the app

**OAuth & Permissions** — add these Bot Token Scopes:
- `channels:history` — read messages in public channels
- `channels:read` — view basic channel info
- `chat:write` — send messages
- `commands` — add slash commands
- `reactions:write` — add emoji reactions
- `users:read` — resolve user display names

**Socket Mode** — enable it under **Settings → Socket Mode**

**App-Level Token** — under **Settings → Basic Information → App-Level Tokens**, generate a token with the `connections:write` scope

**Event Subscriptions** — enable and subscribe to the `message.channels` bot event

**Slash Commands** — create a `/wordle` command (the request URL doesn't matter with Socket Mode, but you can use `https://localhost`)

### 3. Install to workspace

Go to **OAuth & Permissions** and click **Install to Workspace**. Copy the **Bot User OAuth Token** (`xoxb-...`).

### 4. Run the bot

```bash
git clone https://github.com/yoclaire/wordlebot-for-slack.git
cd wordlebot-for-slack
cp .env.example .env
# Edit .env with your tokens
docker compose up -d
```

Invite the bot to a channel and start pasting Wordle shares.

### 5. Backfill (optional)

If the channel already has Wordle scores, run `/wordle backfill` to import them.

## Data

Scores are stored as JSON in `./data/scores.json`. The file is human-readable and easy to back up. Achievements and config (like which channel to post scheduled messages to) are in `./data/config.json`.

## License

MIT
