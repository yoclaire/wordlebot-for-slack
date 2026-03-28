# Secret Crab Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hidden easter egg toggled by crab reactji that transforms the bot into a deadpan marine biologist — crab-themed commentary, real NorCal surf reports, all reactions become crab, everything obfuscated in the repo.

**Architecture:** In-memory boolean toggle activated by `reaction_added` event on bot messages. Conditional branches in existing functions swap content from a new `supplemental.json` data file. Marine weather fetched from Open-Meteo Marine API (free, no key). All naming uses bland `_alt_active` / `SUPPLEMENTAL` conventions — no "crab" references in code.

**Tech Stack:** Python 3.12, slack-bolt (existing), Open-Meteo Marine API, urllib (existing)

**Prerequisite — Slack App Config (manual):** Before testing, the Slack app needs `reactions:read` scope and `reaction_added` event subscription enabled in the Slack API dashboard. Reinstall the app if scopes changed.

---

### Task 1: Create supplemental content data file

**Files:**
- Create: `supplemental.json`

This is the crab content pool — all alternative templates stored under obfuscated keys that mirror `commentary.json` structure. The file name is intentionally bland.

- [ ] **Step 1: Create `supplemental.json`**

```json
{
  "trigger_reaction": "crab",
  "reaction_override": "crab",
  "mode_on": "CRAB MODE ACTIVATED",
  "mode_off": "CRAB MODE DEACTIVATED",

  "score_1": [
    "A *Portunus pelagicus* doesn't need a second strike. Neither, apparently, do you.",
    "The mantis shrimp strikes at 23 m/s. This was comparable efficiency.",
    "Precision reminiscent of *Ocypode* hunting by moonlight. No wasted movement.",
    "The coconut crab opens a coconut in two motions. You solved this in one.",
    "Efficient. Like *Callinectes sapidus* intercepting prey mid-current. Clean work.",
    "The Japanese spider crab wastes nothing. Today, neither did you.",
    "Stone crabs crush oyster shells on the first attempt. This was noted.",
    "A textbook ambush. The *Charybdis hellerii* would approve.",
    "One attempt. The *Birgus latro* doesn't hesitate either.",
    "Clinical. Like a pistol shrimp's cavitation bubble. One shot, total destruction."
  ],
  "score_2": [
    "Two attempts. The blue crab dispatches a mussel in roughly the same.",
    "Efficient lateral movement. A *Carcinus maenas* covers ground this way.",
    "The Dungeness crab rarely needs more than two passes through a kelp bed.",
    "A fiddler crab waves twice and the message is received. Comparable.",
    "Swift. The *Ovalipes ocellatus* would find no inefficiency here.",
    "Two guesses. The decorator crab places each sponge with similar precision.",
    "The red rock crab identifies prey in two sweeps of its antennae. Noted.",
    "Economical. Like the mating display of *Uca pugilator* — brief and effective."
  ],
  "score_3": [
    "Methodical. A *Carcinus maenas* working the tide pools with purpose.",
    "The reliable approach of a hermit crab selecting its next shell. Considered. Deliberate.",
    "Like the fiddler crab's daily feeding rhythm — nothing rushed, nothing wasted.",
    "A steady lateral approach. The *Pachygrapsus crassipes* navigates the rocks this way.",
    "Consistent as the tides. A three-guess solve is the backbone of any colony.",
    "The Dungeness crab doesn't rush. It processes. Much like this solve.",
    "You foraged through the possibilities the way *Uca* sifts sediment. Respectably.",
    "Solid. The red rock crab would find no fault in this approach."
  ],
  "score_4": [
    "Four passes. The *Grapsus grapsus* sometimes takes four tide cycles to find its preferred algae patch.",
    "A hermit crab may inspect four shells before committing. This is not indecision. It is thoroughness.",
    "The shore crab works methodically. Four attempts is within normal foraging parameters.",
    "Adequate coverage of the search area. The *Pagurus samuelis* takes a similar approach.",
    "Four. The Jonah crab (*Cancer borealis*) doesn't judge. Neither do we. Officially.",
    "Like the box crab's deliberate excavation technique. Not fast, but it works.",
    "The *Hemigrapsus nudus* completes its burrow in roughly four digging cycles. On schedule.",
    "Four attempts. Within one standard deviation of the colony mean."
  ],
  "score_5": [
    "The soft-shell crab is at its most vulnerable mid-molt. You looked like that out there.",
    "Sometimes survival is the achievement. Ask any *Pagurus* during a shell shortage.",
    "The *Birgus latro* retreats to its burrow when conditions are unfavorable. No shame in that.",
    "A ghost crab running from a shorebird. You made it. That's what counts.",
    "Molting is a dangerous process. Not every crab survives it. But you did. Barely.",
    "The horseshoe crab has survived 450 million years by not giving up. Respect.",
    "Even the *Gecarcoidea natalis* loses a few on the journey to sea. You arrived.",
    "The hermit crab between shells — exposed, vulnerable, but still moving forward."
  ],
  "score_6": [
    "Six attempts. The *Eriocheir sinensis* sometimes takes six tide cycles to cross an estuary. It always arrives.",
    "A spider crab navigating a gauntlet of sea stars. Harrowing. But you're here.",
    "The pea crab spends its entire life inside a mussel. Confined, but alive. Like this solve.",
    "The last possible attempt. The *Calappa* retreats into its shell and simply waits. Bold strategy.",
    "We've seen king crabs survive worse conditions. Barely.",
    "The red crab migration across Christmas Island has a high attrition rate. You are not a statistic today.",
    "Six. In crab terms, this is the equivalent of molting in open water. High risk, low margin.",
    "Like a coconut crab descending from the palm on the sixth attempt. Technically successful."
  ],
  "score_x": [
    "The ocean does not negotiate. Neither, apparently, did today's puzzle.",
    "In the wild, the molt failure rate for *Cancer pagurus* approaches 30%. These things happen.",
    "A *Paralithodes camtschaticus* caught outside its depth range. The water was too warm.",
    "The Christmas Island red crabs lose thousands on the migration. Nature is indifferent.",
    "Habitat loss claims even the strongest. Today's word was your rising sea level.",
    "The coconut crab's armor offers no protection against some predators. Today was that predator.",
    "Not every larva reaches the shore. The pelagic phase is unforgiving.",
    "The *Eriocheir sinensis* swims against the current for months. Sometimes the current wins.",
    "A failed molt. The old carapace did not release. There is no recovering from this.",
    "The research team has documented the loss. We will continue monitoring."
  ],

  "hard_mode_good": [
    "Hard mode with a low score. The *Birgus latro* climbs 6-meter palms for coconuts. Comparable ambition, comparable success.",
    "Hard mode. The decorator crab adds complexity voluntarily. Respect.",
    "Voluntary constraint, excellent result. The way a spider crab navigates the reef — the hard route, by choice."
  ],
  "hard_mode_survive": [
    "Even armored crabs take damage during the molt. Hard mode survival is its own reward.",
    "Hard mode. Like the hermit crab choosing a shell slightly too small. It works. It's not comfortable.",
    "Hard mode at this score is the crab equivalent of foraging during a storm surge. You lived."
  ],
  "hard_mode_fail": [
    "Hard mode X. The hermit crab in an ill-fitting shell. Ambitious protection, inadequate coverage.",
    "A bold choice. The coconut crab does not always reach the top of the palm.",
    "Hard mode failure. The decorated crab's camouflage is not always sufficient."
  ],

  "streak_building": [
    "{streak} consecutive days observed. The specimen has established a routine.",
    "Day {streak} of unbroken activity. Foraging patterns are consistent.",
    "{streak}-day observation streak. Behavioral consistency noted."
  ],
  "streak_hot": [
    "{streak} days without interruption. Remarkable endurance for this species.",
    "Day {streak}. The specimen shows no signs of fatigue or retreat.",
    "{streak} consecutive foraging days. This exceeds typical *Carcinus maenas* patterns."
  ],
  "streak_epic": [
    "{streak} days. This exceeds all documented behavioral records for the colony.",
    "Day {streak}. At this point we've stopped counting and started publishing.",
    "{streak} consecutive days. The other researchers don't believe our data."
  ],

  "close_call_on_streak": [
    "A near-miss. The specimen nearly failed to forage. Observation streak: {streak} days.",
    "6/6 — the crab equivalent of barely returning before the tide. {streak}-day streak holds.",
    "Survival margins that thin concern the research team. {streak} days observed."
  ],
  "comeback_strong": [
    "Notable recovery. From {prev_score}/6 to {score}/6. The molt appears complete.",
    "Significant behavioral improvement. {prev_score}/6 to {score}/6. Conditions have shifted.",
    "A *Callinectes sapidus* emerging from a damaged shell, stronger. {prev_score}/6 to {score}/6."
  ],
  "comeback_ok": [
    "Marginal improvement over yesterday's {prev_score}/6. The tide is turning.",
    "Better foraging conditions today. {prev_score}/6 to {score}/6.",
    "Recovery trajectory is positive after yesterday's {prev_score}/6."
  ],
  "hot_hand": [
    "This specimen is exhibiting peak foraging efficiency. *{recent_avg:.1f}* avg vs *{overall_avg:.1f}* career.",
    "Heightened performance period detected. *{recent_avg:.1f}* recent vs *{overall_avg:.1f}* overall.",
    "The crab equivalent of prime season. *{recent_avg:.1f}* lately vs *{overall_avg:.1f}* career."
  ],
  "cold_spell": [
    "Performance decline noted. *{recent_avg:.1f}* avg vs *{overall_avg:.1f}* career. Environmental stress suspected.",
    "Suboptimal foraging. *{recent_avg:.1f}* recent vs *{overall_avg:.1f}* overall. Water conditions may be a factor.",
    "The specimen appears sluggish. *{recent_avg:.1f}* vs *{overall_avg:.1f}* career. Post-molt lethargy?"
  ],
  "personal_best": [
    "Peak performance: best observed result in {games} foraging sessions.",
    "A new benchmark. {games} observations and this is the most efficient yet.",
    "Best performance in {games} sessions. The specimen has optimized its approach."
  ],

  "morning_briefing": [
    "Tidal conditions along the Northern California coast are favorable this morning. The intertidal zone is active.",
    "The *Pachygrapsus crassipes* is returning to the upper intertidal with the receding tide. A productive night.",
    "Dawn along the California coast. The purple shore crabs are settling into crevices after a night of foraging.",
    "Water temperature is holding steady. The Dungeness crab molt season approaches.",
    "The *Emerita analoga* — sand crabs — are already filtering the morning surf.",
    "Ghost crabs have retreated to their burrows ahead of daylight. Smart.",
    "The kelp forests off the NorCal coast are active this morning. Spider crabs grazing among the holdfasts.",
    "Shore crab activity peaks at dawn and dusk. The crevices along Bodega Head are bustling.",
    "Tidepools along the Sonoma coast are refreshing as the morning high tide recedes. A good sign.",
    "Hermit crabs along the Northern California coast are beginning their daily shell inspections.",
    "Overnight currents have brought fresh nutrients to the nearshore zone. Foraging conditions: excellent.",
    "The *Lopholithodes mandtii* — box crab — has buried itself in the sand for the day. As is tradition.",
    "Morning fog along the coast. The crabs are unbothered. Visibility is irrelevant when you have antennae."
  ],
  "evening_briefing": [
    "As darkness falls along the Pacific, nocturnal foraging begins across the intertidal zone.",
    "The *Pachygrapsus crassipes* emerges for its evening forage. Efficient. Reliable.",
    "Bioluminescent plankton in the deeper waters tonight. The crabs pay no attention. They have work to do.",
    "Nightfall brings the *Pugettia producta* out of the kelp canopy. Feeding time.",
    "The ghost crabs venture further from their burrows after sunset. The beach is theirs now.",
    "Moonlight on the Pacific. The sand crabs continue filtering regardless.",
    "Shore crabs have expanded their patrol radius now that visual predators have retired.",
    "The Dungeness fleet would be heading out about now. The crabs are, as always, unimpressed.",
    "Evening water temperature dropping 1-2C along the shelf. The deeper specimens are adjusting position.",
    "Under cover of darkness, the hermit crabs begin their nightly shell exchange negotiations.",
    "The *Hemigrapsus oregonensis* is most active in the next four hours. We will be monitoring.",
    "Nighttime is when the real work happens in the intertidal. The crabs understand this.",
    "The porcelain crabs have emerged from beneath their rocks. The evening shift begins."
  ],

  "shame": [
    "Concerning: {names} have not emerged from their burrows today. Possible molting in progress.",
    "No activity detected from {names}. Shell-dwelling behavior at this hour may indicate environmental stress.",
    "{names}: prolonged burrowing is atypical for this time of year. We're monitoring the situation.",
    "The colony notes the absence of {names}. Extended retreat behavior warrants observation.",
    "Still no surface activity from {names}. If they're molting, best not to disturb them. If not — concerning.",
    "{names} remain below the sediment line. The other crabs have managed to forage today.",
    "A healthy crab emerges daily. {names} have not emerged. We are withholding judgment. For now.",
    "The tide has come and gone. {names} were not observed at the surface.",
    "Field notes: {names} unaccounted for during today's survey. Predation has not been ruled out.",
    "The research team is mildly concerned about {names}. Burrowing durations exceeding 18 hours are atypical."
  ],

  "all_played": [
    "All specimens have surfaced and foraged successfully today. Colony health: optimal.",
    "Full colony participation detected. The intertidal zone has been thoroughly worked.",
    "Every member of the colony has reported in. The reef is productive today.",
    "All specimens accounted for. Foraging efficiency across the colony appears normal.",
    "The colony has completed its daily survey of the word pool. All survived.",
    "Full emergence. A sign of healthy habitat conditions and adequate resources."
  ],

  "wrap_intro": [
    "Evening marine conditions report. Also, your Wordle scores, which some of you seem to care about.",
    "The sun sets over the Pacific. The crabs are stirring. Here are today's results, I suppose.",
    "Nighttime activity has commenced along the coast. In less important news, today's Wordle:",
    "The swell has settled for the evening. Time to review the colony's puzzle performance.",
    "Marine forecast is stable. Now, these scores:",
    "End of day field report. Marine observations first, then the Wordle data.",
    "The research station logs the following. Marine conditions are detailed below. Wordle results are also, unfortunately, included."
  ],

  "difficulty": {
    "easy": "An easy forage. Barely had to leave the burrow.",
    "solid": "Required some lateral movement across the reef. A solid day's work.",
    "tough": "Treacherous conditions out there. Many crabs struggled today.",
    "brutal": "A catastrophic molt day. Conditions were hostile."
  },

  "weekly_intro": [
    "Weekly colony assessment. The dominant specimen has been identified.",
    "Seven-day field survey complete. Population ranking follows.",
    "The weekly territorial evaluation is concluded. Results:"
  ],
  "monthly_intro": [
    "End of month field notes. Population performance summary for the research log.",
    "Monthly colony census complete. Behavioral data has been compiled.",
    "The monthly marine survey concludes. Colony standings are as follows."
  ],
  "yearly_intro": [
    "Annual marine census report. Colony statistics have been finalized.",
    "The yearly population assessment is complete. We present the findings.",
    "Year-end field report. The colony's annual performance has been documented."
  ],

  "general_facts": [
    "The Japanese spider crab has a leg span of up to 3.7 meters. The largest living arthropod. Worth knowing.",
    "Horseshoe crabs are not true crabs. They're more closely related to spiders. This changes nothing about our work here.",
    "The coconut crab can lift up to 28 kg. The strongest grip of any crustacean. Relevant to today's difficulty, arguably.",
    "Crabs have been walking sideways for approximately 200 million years. If the approach works, don't fix it.",
    "The yeti crab farms bacteria on its own claws for sustenance. Self-sufficient. Unlike some members of this colony.",
    "A female blue crab mates only once but stores sperm for multiple clutches. Efficient resource management.",
    "The decorator crab attaches sponges and algae to its shell for camouflage. Methodical. Strategic.",
    "Fiddler crabs regenerate lost claws. The replacement is always smaller. Adaptation has costs.",
    "The pea crab lives inside oysters and mussels. A controversial lifestyle choice, but effective.",
    "Red king crabs can live up to 30 years in cold waters. Longevity rewards consistency.",
    "Sally Lightfoot crabs can run in all four directions simultaneously. Versatile.",
    "Crabs communicate through drumming and claw-waving. Complex signals. No vocalization needed.",
    "The Dungeness crab fishery contributes approximately $220 million annually to the West Coast economy. The crabs receive none of it.",
    "The porcelain crab has the fastest appendage movement in the animal kingdom. Faster than the mantis shrimp by acceleration.",
    "The *Cardisoma guanhumi* can migrate up to 8 km from the ocean and still return. Impressive navigation."
  ],

  "surf_spots": {
    "Mavericks": [37.4936, -122.4967],
    "Ocean Beach": [37.7609, -122.5108],
    "Steamer Lane": [36.9519, -122.0261],
    "Linda Mar": [37.5966, -122.5014],
    "Pleasure Point": [36.9633, -121.9753],
    "Bolinas": [37.9094, -122.6858],
    "Fort Point": [37.8106, -122.4770],
    "Stinson Beach": [37.8999, -122.6420]
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add supplemental.json
git commit -m "feat: add supplemental response templates"
```

---

### Task 2: Add content loader, Zalgo utility, and Dockerfile update

**Files:**
- Modify: `app.py:39-40` (near COMMENTARY loader)
- Modify: `app.py` (add Zalgo function near commentary helpers)
- Modify: `Dockerfile:6`
- Modify: `test_app.py:59-85` (add new imports)
- Modify: `test_app.py` (add new test classes)

- [ ] **Step 1: Write failing tests for supplemental loader and Zalgo**

Add to `test_app.py` after the existing test imports (around line 85):

```python
SUPPLEMENTAL = _test_globals.get("SUPPLEMENTAL", {})
_apply_diacritics = _test_globals.get("_apply_diacritics")
_format_conditions = _test_globals.get("_format_conditions")
```

Add test classes at the end of the file (before `if __name__`):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app -v 2>&1 | tail -20`
Expected: FAIL — `SUPPLEMENTAL` is empty dict, `_apply_diacritics` is None

- [ ] **Step 3: Add supplemental loader to app.py**

Add after the COMMENTARY loader (around line 40):

```python
SUPPLEMENTAL_FILE = Path(__file__).parent / "supplemental.json"
SUPPLEMENTAL = json.loads(SUPPLEMENTAL_FILE.read_text()) if SUPPLEMENTAL_FILE.exists() else {}
```

- [ ] **Step 4: Add `_apply_diacritics` function to app.py**

Add near the other commentary helper functions (around line 200, after `get_commentary`):

```python
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
```

- [ ] **Step 5: Update Dockerfile to include supplemental.json**

Change line 6 from:
```dockerfile
COPY app.py commentary.json ./
```
to:
```dockerfile
COPY app.py commentary.json supplemental.json ./
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app -v 2>&1 | tail -30`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add app.py test_app.py Dockerfile
git commit -m "feat: add supplemental content loader and text effects"
```

---

### Task 3: Add marine weather fetch and formatter

**Files:**
- Modify: `app.py` (add after `fetch_wordle_answer`, around line 80)
- Modify: `test_app.py` (add test class)

- [ ] **Step 1: Write failing test for `_format_conditions`**

Add import in `test_app.py` near line 85:
```python
_format_conditions = _test_globals.get("_format_conditions")
```

(This was already added in Task 2 Step 1. If not, add it now.)

Add test class:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app.TestFormatConditions -v`
Expected: FAIL — `_format_conditions` is None

- [ ] **Step 3: Add surf spot data and functions to app.py**

Add after `fetch_wordle_answer` (around line 80):

```python
_SURF_SPOTS = {
    "Mavericks": (37.4936, -122.4967),
    "Ocean Beach": (37.7609, -122.5108),
    "Steamer Lane": (36.9519, -122.0261),
    "Linda Mar": (37.5966, -122.5014),
    "Pleasure Point": (36.9633, -121.9753),
    "Bolinas": (37.9094, -122.6858),
    "Fort Point": (37.8106, -122.4770),
    "Stinson Beach": (37.8999, -122.6420),
}


def _format_conditions(data: dict, spot_name: str) -> str:
    """Format marine API response into a conditions report."""
    current = data.get("current", {})
    wave_h = current.get("wave_height")
    swell_h = current.get("swell_wave_height")
    swell_p = current.get("swell_wave_period")
    swell_d = current.get("swell_wave_direction")

    if wave_h is None:
        return f"*{spot_name}*: No data available."

    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    compass = dirs[round(swell_d / 22.5) % 16] if swell_d is not None else ""

    if swell_h is not None and swell_p is not None:
        return (
            f"*{spot_name}*: {swell_h}m swell at {swell_p}s from the {compass}. "
            f"Combined wave height {wave_h}m."
        )
    return f"*{spot_name}*: {wave_h}m wave height."


def _fetch_marine_conditions() -> str | None:
    """Fetch current marine conditions for a random surf spot."""
    spot_name = random.choice(list(_SURF_SPOTS.keys()))
    lat, lon = _SURF_SPOTS[spot_name]
    url = (
        f"https://marine-api.open-meteo.com/v1/marine?"
        f"latitude={lat}&longitude={lon}"
        f"&current=wave_height,swell_wave_height,swell_wave_period,swell_wave_direction"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wordlebot"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return _format_conditions(data, spot_name)
    except Exception as e:
        logging.warning(f"Could not fetch marine conditions: {e}")
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app.TestFormatConditions -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "feat: add marine conditions data source"
```

---

### Task 4: Add reaction event handler and toggle mechanism

**Files:**
- Modify: `app.py:1296-1303` (add to `__main__` block)
- Modify: `app.py` (add global flag near other globals, add event handler)

This task adds Slack-dependent code (reaction handler, auth.test call) that is not unit-testable. Manual testing instructions provided.

- [ ] **Step 1: Add global toggle variable**

Add after the `SUPPLEMENTAL` loader (right after the line that loads supplemental.json):

```python
_alt_active = False
_self_id = None
```

- [ ] **Step 2: Add reaction event handler**

Add after the `@app.command("/wordle")` handler function (before `if __name__ == "__main__"`):

```python
@app.event("reaction_added")
def _handle_reaction_event(event, say):
    global _alt_active
    if _self_id is None:
        return
    if event.get("item_user") != _self_id:
        return
    trigger = SUPPLEMENTAL.get("trigger_reaction", "")
    if not trigger or event.get("reaction") != trigger:
        return

    _alt_active = not _alt_active
    channel = event.get("item", {}).get("channel")
    if not channel:
        return

    emoji = SUPPLEMENTAL.get("reaction_override", trigger)
    if _alt_active:
        label = _apply_diacritics(SUPPLEMENTAL.get("mode_on", ""))
        app.client.chat_postMessage(channel=channel, text=f":{emoji}: {label} :{emoji}:")
    else:
        label = _apply_diacritics(SUPPLEMENTAL.get("mode_off", ""))
        app.client.chat_postMessage(channel=channel, text=f":{emoji}: {label} :{emoji}:")
```

- [ ] **Step 3: Add bot user ID retrieval at startup**

Modify the `if __name__ == "__main__"` block. Change:

```python
if __name__ == "__main__":
    logging.info("Starting Wordle bot...")
```

to:

```python
if __name__ == "__main__":
    logging.info("Starting Wordle bot...")

    try:
        _self_id = app.client.auth_test()["user_id"]
        logging.info(f"Bot user ID: {_self_id}")
    except Exception as e:
        logging.warning(f"Could not retrieve bot user ID: {e}")
```

- [ ] **Step 4: Manual test**

Deploy the bot and test:
1. Post a message that triggers the bot (e.g., a Wordle score)
2. Add a crab reactji to the bot's reply
3. Verify the bot posts "CRAB MODE ACTIVATED" with Zalgo text
4. Add another crab reactji to any bot message
5. Verify the bot posts "CRAB MODE DEACTIVATED"

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: add reaction-based mode toggle"
```

---

### Task 5: Alt mode — reactions and score commentary

**Files:**
- Modify: `app.py:1126-1151` (handle_wordle_score reaction block)
- Modify: `app.py:201-204` (get_commentary)
- Modify: `app.py:657-716` (get_smart_commentary)
- Modify: `test_app.py` (add alt mode tests)

- [ ] **Step 1: Write failing tests for alt mode commentary**

Add test class to `test_app.py`:

```python
class TestAltModeCommentary(unittest.TestCase):
    def setUp(self):
        self._original = _test_globals.get("_alt_active", False)
        _test_globals["_alt_active"] = True

    def tearDown(self):
        _test_globals["_alt_active"] = self._original

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
        shame, has_missing = build_shame_list(scores)
        self.assertTrue(has_missing)
        found_alt = any(
            phrase in shame
            for phrase in ["emerged", "burrow", "molting", "colony", "sediment",
                           "surface", "observation", "burrowing", "tide",
                           "Predation", "survey", "specimen"]
        )
        self.assertTrue(found_alt, f"Shame message doesn't look alt-themed: {shame}")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app.TestAltModeCommentary -v`
Expected: FAIL — `get_commentary` still returns normal templates

- [ ] **Step 3: Modify `get_commentary` for alt mode**

Change `get_commentary` (around line 201):

```python
def get_commentary(score: str) -> str | None:
    key = f"score_{score}" if score != "X" else "score_x"
    source = SUPPLEMENTAL if _alt_active and key in SUPPLEMENTAL else COMMENTARY
    templates = source.get(key, [])
    return random.choice(templates) if templates else None
```

- [ ] **Step 4: Modify `get_smart_commentary` hard mode + context selection**

In `get_smart_commentary` (around line 670-680), change the hard mode block:

```python
    if hard_mode:
        if score == "X":
            key = "hard_mode_fail"
        elif score_val <= 4:
            key = "hard_mode_good"
        else:
            key = "hard_mode_survive"
        source = SUPPLEMENTAL if _alt_active and key in SUPPLEMENTAL else COMMENTARY
        templates = source.get(key, [])
        if templates:
            context.append(random.choice(templates))
```

The contextual functions (`check_streak`, `check_hot_cold`, `check_comeback`, `check_personal_best`, `close_call_on_streak`) each need to swap their source dict. Apply the same pattern to each.

In `check_streak` (around line 214-228), change template lookups:

```python
    if current >= 7 and current % 7 == 0:
        key = "streak_epic" if current >= 14 else "streak_hot"
        source = SUPPLEMENTAL if _alt_active and key in SUPPLEMENTAL else COMMENTARY
        templates = source.get(key, [])
        ...
    if current == 3:
        source = SUPPLEMENTAL if _alt_active and "streak_building" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("streak_building", [])
        ...
```

In `check_hot_cold` (around line 243-251), change template lookups:

```python
    if diff >= 1.0:
        source = SUPPLEMENTAL if _alt_active and "hot_hand" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("hot_hand", [])
        ...
    if diff <= -1.0:
        source = SUPPLEMENTAL if _alt_active and "cold_spell" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("cold_spell", [])
        ...
```

In `check_comeback` (around line 623-632), change template lookups:

```python
    if prev >= 6 and curr <= 3:
        source = SUPPLEMENTAL if _alt_active and "comeback_strong" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("comeback_strong", [])
        ...
    if prev >= 5 and curr < prev:
        source = SUPPLEMENTAL if _alt_active and "comeback_ok" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("comeback_ok", [])
        ...
```

In `check_personal_best` (around line 650-653), change template lookup:

```python
    if current < min(recent):
        source = SUPPLEMENTAL if _alt_active and "personal_best" in SUPPLEMENTAL else COMMENTARY
        templates = source.get("personal_best", [])
        ...
```

In `get_smart_commentary`, the close call block (around line 688-694):

```python
    if score_val == 6:
        _, puzzles = get_user_scores(scores, user_id)
        current_streak, _ = calc_streak(puzzles)
        if current_streak >= 3:
            source = SUPPLEMENTAL if _alt_active and "close_call_on_streak" in SUPPLEMENTAL else COMMENTARY
            templates = source.get("close_call_on_streak", [])
            if templates:
                context.append(random.choice(templates).format(streak=current_streak))
```

- [ ] **Step 5: Modify `build_shame_list` for alt mode**

In `build_shame_list` (around line 595-596), change template selection:

```python
    source = SUPPLEMENTAL if _alt_active and "shame" in SUPPLEMENTAL else COMMENTARY
    templates = source.get("shame", ["{names}: play wordle already"])
    return random.choice(templates).format(names=names), True
```

- [ ] **Step 6: Modify score reactions in `handle_wordle_score`**

In `handle_wordle_score` (around line 1127-1151), after the reaction dict and before `reactions_add`:

```python
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
        if _alt_active and override:
            reaction = override

        app.client.reactions_add(
            channel=message["channel"],
            timestamp=message["ts"],
            name=reaction,
        )

        if hard_mode and not (_alt_active and override):
            app.client.reactions_add(
                channel=message["channel"],
                timestamp=message["ts"],
                name="star",
            )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app -v 2>&1 | tail -30`
Expected: All tests PASS (including new alt mode tests and all existing tests unchanged)

- [ ] **Step 8: Commit**

```bash
git add app.py test_app.py
git commit -m "feat: add alternative commentary and reaction modes"
```

---

### Task 6: Alt mode — scheduled posts (morning nudge + daily wrap)

**Files:**
- Modify: `app.py:1010-1099` (schedule_daily_tasks)
- Modify: `app.py:386-429` (build_daily_summary)

- [ ] **Step 1: Write test for alt mode daily summary**

Add test class to `test_app.py`:

```python
class TestAltModeDailySummary(unittest.TestCase):
    def setUp(self):
        self._original = _test_globals.get("_alt_active", False)
        _test_globals["_alt_active"] = True

    def tearDown(self):
        _test_globals["_alt_active"] = self._original

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app.TestAltModeDailySummary -v`
Expected: FAIL

- [ ] **Step 3: Modify `build_daily_summary` for alt mode**

Change the header (around line 403):

```python
    if _alt_active:
        intros = SUPPLEMENTAL.get("wrap_intro", [])
        header = random.choice(intros) if intros else f"*Puzzle {latest}*"
        lines = [f"{header}\n"]
    else:
        lines = [f"*Wordle {latest} Results*\n"]
```

Change the difficulty section (around line 417-428):

```python
    if all_scores:
        avg = sum(all_scores) / len(all_scores)
        if _alt_active:
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
```

- [ ] **Step 4: Modify morning nudge in `schedule_daily_tasks`**

In the `event_type == "morning"` branch (around line 1044-1054):

```python
            if event_type == "morning":
                if _alt_active:
                    parts = []
                    conditions = _fetch_marine_conditions()
                    if conditions:
                        parts.append(conditions)
                    briefings = SUPPLEMENTAL.get("morning_briefing", [])
                    if briefings:
                        parts.append(random.choice(briefings))
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
```

- [ ] **Step 5: Modify evening wrap in `schedule_daily_tasks`**

In the `event_type == "evening"` branch, after the daily summary post (around line 1065), add evening briefing:

```python
                if not already_posted:
                    summary = build_daily_summary(scores)
                    if summary:
                        app.client.chat_postMessage(channel=channel_id, text=summary)

                    if _alt_active:
                        parts = []
                        conditions = _fetch_marine_conditions()
                        if conditions:
                            parts.append(conditions)
                        briefings = SUPPLEMENTAL.get("evening_briefing", [])
                        if briefings:
                            parts.append(random.choice(briefings))
                        if parts:
                            app.client.chat_postMessage(
                                channel=channel_id,
                                text="\n\n".join(parts),
                            )

                    shame, has_missing = build_shame_list(scores)
                    if has_missing:
                        app.client.chat_postMessage(channel=channel_id, text=shame)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app -v 2>&1 | tail -30`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add app.py test_app.py
git commit -m "feat: add alternative scheduled post content"
```

---

### Task 7: Alt mode — all-played trigger and recaps

**Files:**
- Modify: `app.py:966-1007` (post_all_played_summary)
- Modify: `app.py:812-865` (build_monthly_recap)
- Modify: `app.py:868-935` (build_yearly_recap)
- Modify: `app.py:1077-1083` (weekly champion in scheduler)

- [ ] **Step 1: Modify `post_all_played_summary`**

Change the all-played message (around line 978):

```python
    source = SUPPLEMENTAL if _alt_active and "all_played" in SUPPLEMENTAL else COMMENTARY
    templates = source.get("all_played", ["Everyone's in! Let's see how you all did."])
    app.client.chat_postMessage(
        channel=channel_id,
        text=random.choice(templates) + "\n",
    )
```

- [ ] **Step 2: Modify weekly champion in scheduler**

Change the Sunday night weekly block (around line 1078-1083):

```python
                if now.weekday() == 6:
                    lb = build_leaderboard(scores, days=7)
                    if _alt_active:
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
```

- [ ] **Step 3: Modify `build_monthly_recap`**

Change the header (around line 831):

```python
    month_name = calendar.month_name[month]
    if _alt_active:
        intros = SUPPLEMENTAL.get("monthly_intro", [])
        header = random.choice(intros) if intros else f"Monthly report: {month_name} {year}"
        lines = [f"{header}\n"]
    else:
        lines = [f"📅 *{month_name} {year} Recap*\n"]
```

Change the champion line (around line 838):

```python
    champ_id, champ_scores = ranked[0]
    champ_avg = sum(champ_scores) / len(champ_scores)
    if _alt_active:
        lines.append(f"*Dominant specimen:* <@{champ_id}> — avg *{champ_avg:.1f}* over {len(champ_scores)} foraging sessions\n")
    else:
        lines.append(f"👑 *Champion:* <@{champ_id}> — avg *{champ_avg:.1f}* over {len(champ_scores)} games\n")
```

Add a general fact at the end when in alt mode (before the return):

```python
    if _alt_active:
        facts = SUPPLEMENTAL.get("general_facts", [])
        if facts:
            lines.append(f"\n_{random.choice(facts)}_")

    return "\n".join(lines)
```

- [ ] **Step 4: Modify `build_yearly_recap`**

Change the header (around line 887):

```python
    if _alt_active:
        intros = SUPPLEMENTAL.get("yearly_intro", [])
        header = random.choice(intros) if intros else f"Annual report: {year}"
        lines = [f"{header}\n"]
    else:
        lines = [f"🎆 *{year} Wordle Year in Review*\n"]
```

Change the Player of the Year line (around line 892):

```python
    if _alt_active:
        lines.append(f"*Alpha specimen:* <@{champ_id}> — avg *{champ_avg:.1f}* over {len(champ_scores)} sessions\n")
    else:
        lines.append(f"👑 *Player of the Year:* <@{champ_id}> — avg *{champ_avg:.1f}* over {len(champ_scores)} games\n")
```

Add a general fact at the end when in alt mode (before the return):

```python
    if _alt_active:
        facts = SUPPLEMENTAL.get("general_facts", [])
        if facts:
            lines.append(f"\n_{random.choice(facts)}_")

    return "\n".join(lines)
```

- [ ] **Step 5: Run all tests**

Run: `cd /home/human/services/wordlebot-for-slack && python -m unittest test_app -v`
Expected: All tests PASS

- [ ] **Step 6: Run linter**

Run: `cd /home/human/services/wordlebot-for-slack && pip install ruff -q && ruff check .`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "feat: add alternative content for group triggers and recaps"
```
