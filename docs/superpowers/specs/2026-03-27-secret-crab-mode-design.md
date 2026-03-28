# Secret Crab Mode — Design Spec

## Overview

A hidden easter egg that transforms the bot's entire personality into a deadpan marine biologist who happens to also track Wordle scores. Toggled secretly via crab reactji. Obfuscated in the codebase so it's not obvious from the repo.

## Trigger & State

- **Toggle on/off:** User adds a `crab` reactji to any message authored by the bot
- **Activation:** Bot posts in-channel: `CRAB MODE ACTIVATED` (with Zalgo text and crab emoji)
- **Deactivation:** Bot posts in-channel: `CRAB MODE DEACTIVATED`
- **State:** In-memory boolean only. Dies on restart. Not persisted to config.json.
- **No mention** in `/wordle help`, README, or any discoverable documentation

## Personality

The bot does not know it's being funny. It has simply always been deeply invested in crustacean biology and coastal ecosystems. Wordle tracking is incidental — something it's obligated to do but clearly less interested in than the marine world.

**Tone:** Matter-of-fact. Serious. No puns. No dad jokes. No winking at the camera. The humor comes entirely from the sincerity and the unreasonable depth of knowledge.

**Emoji usage:** Every template leads with 🦀 or 🌊, matching the frequency and position of emoji in normal mode. 🦀 is the primary emoji (used where normal bot uses any emoji). 🌊 is used where ocean/wave context is appropriate. The wall of uniform 🦀🦀🦀 where there used to be variety IS part of the joke.

**Example voice:** "Mavericks reporting 1.4m swell at 9s intervals. Water temp: 12.8C. Conditions favorable for foraging along the reef. Also, here are today's Wordle results, I suppose."

## What Changes During Crab Mode

### Reactions

All score-based emoji reactions become `crab`. No exceptions — whether you got a 1/6 or an X/6, you get a crab. Hard mode star is also replaced with crab.

### Score Commentary

Deadpan crab-themed commentary replaces normal score commentary. Crab facts should be contextually relevant to the score:

- **Low scores (1-2):** Efficient predator energy. References to ambush hunters, precise claw strikes.
- **Mid scores (3-4):** Steady, methodical. Tidal foraging, patient scavenging, reliable navigation.
- **High scores (5-6):** Survival-focused. Molting vulnerability, defensive behaviors, retreat to burrows.
- **X (fail):** The harsh realities of marine life. Predation, habitat loss, failed molts.

All facts should be **accurate** — real species referenced by Latin name, real behaviors, real biology.

### Morning Nudge (8am)

Transforms into a morning marine briefing. Contextually relevant to morning/dawn:

- **Real surf report:** Fetch marine weather from Open-Meteo Marine API (free, no API key). Wave height, swell period, water temperature for a relevant coastal location.
- **Dawn-relevant crab facts:** Nocturnal species returning to burrows, dawn foraging behaviors, tidal patterns, early-morning predator avoidance.
- Yesterday's Wordle answer mentioned as an afterthought.

### Daily Wrap (10pm)

Evening-themed crab content wrapping the day's scores:

- **Nighttime crab facts:** Nocturnal foraging activity, bioluminescence in deep-sea species, moonlight navigation, evening tidal shifts.
- **Real marine conditions** if available (evening update).
- Scores presented but the bot is clearly more engaged with the marine content.
- Difficulty rating reframed in crab terms.

### Shame List

Players who haven't played are crabs who haven't emerged from their burrows. Delivered with the concerned tone of a marine biologist observing abnormal behavior in a colony:

- Speculation about whether they're molting (vulnerable, best not to disturb)
- Concern about possible predator activity in the area
- Notes on how shell-dwelling behavior can indicate stress

### Weekly/Monthly/Yearly Recaps

If a recap triggers during crab mode, it should also be crab-themed. Same data, crab framing.

### All-Played Trigger

When all active players complete the puzzle, the celebration is crab-themed. The colony has successfully foraged for the day.

## Crab Knowledge Pool

**Target: 100+ unique crab facts/observations.** This is not a shallow gag. Categories:

- **Species profiles:** Real species with Latin names, habitats, behaviors. Cover a range — coconut crabs, blue crabs, horseshoe crabs, fiddler crabs, spider crabs, hermit crabs, etc.
- **Behavioral biology:** Molting cycles, mating rituals, territorial disputes, communication (claw waving, drumming), social hierarchies.
- **Ecology & habitat:** Tide pool ecosystems, mangrove forests, deep-sea vents, coral reefs, estuaries.
- **Seasonal awareness:** What crabs are actually doing at different times of year — migration, spawning, overwintering.
- **Conservation:** Habitat loss, ocean acidification impacts on shells, invasive species, delivered with genuine concern.
- **Historical/cultural:** Crabs in human history, fisheries, fossil record.

Facts should be **tagged by time-of-day relevance** (morning, evening, general) so the bot can match them to the context of the post.

## Real Marine Data

**API:** Open-Meteo Marine Weather API (`https://marine-api.open-meteo.com/v1/marine`)
- Free, no API key required
- Parameters: wave height, swell period, swell direction, water temperature
- Location: Northern California surf spots only. Rotate between well-known NorCal breaks (e.g., Mavericks, Ocean Beach SF, Steamer Lane, Pacifica, Pleasure Point, Bolinas). Pick one at random per report.
- **Failure handling:** If the API is down, the bot does not break. It simply omits the surf report and proceeds with crab facts. No error messages to the channel.

## Obfuscation

The implementation must not be obvious to someone browsing the GitHub repo:

- **No obvious naming:** No `crab_mode` variables, no `# CRAB MODE` comments, no `crab_commentary` keys. Use innocuous names that look like normal bot infrastructure (e.g., a generic-sounding config flag, a bland JSON key).
- **Content storage:** Crab content in `commentary.json` under a non-obvious key, or in a separate file with an innocuous name. The block of crab facts should not be immediately recognizable as an easter egg to a casual reader.
- **Event listener:** The `reaction_added` handler should not scream "easter egg." It should look like generic reaction-handling infrastructure.
- **Code structure:** The crab mode logic should be woven into existing functions rather than isolated in a clearly labeled section.
- **No documentation:** Not in README, not in help output, not in comments that reference "crab" or "easter egg."

## Scope & Non-Goals

- **No score changes.** Crab mode is purely cosmetic/personality.
- **No new slash commands.** The only interface is the reactji toggle.
- **No persistence.** Restart clears crab mode.
- **No achievements.** No crab-related badges or tracking.
- **No leaderboard format changes.** `/wordle` and other slash commands return normal data — crab mode only affects bot-initiated messages and score reactions/commentary.

## Technical Notes

- The bot already uses Socket Mode and handles message events. Adding a `reaction_added` listener is straightforward with slack-bolt.
- The bot's own user ID is needed to check if reacted messages are its own. This can be obtained via `auth.test` at startup.
- Open-Meteo Marine API is HTTP GET with query parameters, similar to the existing NYT API integration for Wordle answers.
- Crab facts pool can be generated and curated, then stored as a data file.
