# Contributing

Thanks for your interest in improving wordlebot-for-slack!

## How to contribute

1. **Open an issue first** — for anything beyond a tiny fix, open an issue to discuss the change before writing code.

2. **Fork and branch** — fork the repo, create a branch from `main`, and make your changes there.

3. **Keep it focused** — one feature or fix per pull request. Small PRs are easier to review.

4. **Test locally** — make sure the bot starts and handles Wordle shares correctly before submitting.
   ```bash
   cp .env.example .env
   # Add your test workspace tokens
   docker compose up --build
   ```

5. **Open a pull request** — describe what you changed and why. All PRs require review before merging.

## Code style

- Keep it simple — this is a single-file bot and that's a feature, not a limitation.
- No additional dependencies without a good reason.
- Match the existing style (no type stubs, no frameworks, minimal abstractions).

## Reporting bugs

Use the [bug report template](https://github.com/yoclaire/wordlebot-for-slack/issues/new?template=bug_report.yml). Include steps to reproduce if possible.

## Ideas and feature requests

Use the [feature request template](https://github.com/yoclaire/wordlebot-for-slack/issues/new?template=feature_request.yml). Describing *why* you want something helps prioritize.
