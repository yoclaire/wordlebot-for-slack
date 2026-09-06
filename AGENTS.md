# Wordlebot agent instructions

A Python Slack Socket Mode bot with JSON state. [README.md](README.md) covers
user-facing behavior, Slack setup and running the app. Read the current source
before asserting a default or suggesting an operational command.
[CLAUDE.md](CLAUDE.md) imports this file so both agents use the same instructions.

## Find the relevant source

| Task | Start here |
|---|---|
| Bot handlers, scoring, persistence and scheduling | [app.py](app.py) |
| Logic tests | [test_app.py](test_app.py) |
| Checks and dependencies | [CI](.github/workflows/ci.yml), [requirements](requirements.txt) |
| Container startup and volumes | [Dockerfile](Dockerfile), [Compose](docker-compose.yml) |
| Environment names | [.env.example](.env.example); never copy live values into Git |

Use `rg --files --hidden -g '!.git' -g '!data/**'` to locate additional files and
search only the relevant source. Historical plans do not authorize new work.
Preserve the existing documentation scope rather than expanding feature
narratives as an incidental part of a maintenance change.

## Work and verification

- Start from freshly fetched `origin/main` in a separate worktree. Preserve local
  edits and application data. Open a PR; Claire squash merges after review and CI.
  Do not push directly to main or merge your own PR. Either agent can implement
  or review; no subagents unless requested. Use your own commit attribution.
- Use the checks in CI appropriate to the change. `python -m unittest test_app -v`
  tests logic without a Slack connection; `ruff check .` checks Python style.
  Use a development environment with the declared dependencies, isolated from
  live state. A docs edit does not need a bot restart or live Slack test.
- Never commit tokens, `.env`, private messages or `data/`. Do not run the bot,
  backfill channels, or send Slack messages merely to verify documentation.

## Thinkserver deployment

The host's managed instances use their own Compose files and systemd units;
this repository's sample Compose file is not the host deployment specification.
Before host work read `/opt/witchhaus/AGENTS.md` (or `CLAUDE.md` until available),
then `/opt/witchhaus/memory/MEMORY.md` for relevant Wordle lessons and the host
runbook for service operations. Those host-private notes and live state are not
part of an app-only clone. Do not edit the timer-managed live source checkout or
mount shared host credentials into a development container.
