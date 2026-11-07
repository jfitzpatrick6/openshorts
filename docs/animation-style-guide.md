# Animation style guide (Animated tab)

**Goal:** the stickpass animations (both **story** and **posed**) should match the
*quality and animation style* of the flat-vector **narrated explainer**: the
five-minute political/economics explainer cartoons (PragerU is the reference
people know). They should be dressed in **our brand palette**: near-black,
warm cream and one red. We copy the *grammar* of that style: one picture per
clause, kinetic type, continuous camera motion and polished character
animation. We never copy a brand: no third-party logos, name cards, taglines
or recognisable characters.

This document is the contract. The storyboarding model, the renderer and code
review all check work against it. Numbers here are defaults: change them here
first, then in code.

---

## 1. The look in one paragraph

A calm, confident narrator explains an argument. Every clause of the narration
gets a picture that literally shows it: a statement becomes a scene, a number
becomes a chart, a concept becomes a visual metaphor. The art is flat vector
and **tonal**: figures and sets are drawn in a warm cream-to-black value ramp
on a near-black stage, like a black-and-white editorial illustration brought to
life. **Red is the only colour.** It marks the one thing the sentence is about.
The camera never stops: it pushes in, trucks across layered parallax sets and
hands off to the next idea with a match cut or a morph. Key words appear on
screen in heavy uppercase sans, with the important word in red. The result
should feel like broadcast motion graphics, not a slideshow.

### Five things that make it read as "that style"

1. **Literal illustration of the voice-over.** If the line says "prices
   doubled", we see a price tag growing to twice its size, not a generic shop.
2. **Black, cream and one red.** Every frame is built from the value ramp in
   §3. Red is spent like money.
3. **Kinetic typography.** Two to five key words per sentence land on screen in
   sync with the voice.
4. **Constant, layered motion.** Parallax depth, and nothing fully static
   for more than about 0.5 s.
5. **Craft in the animation.** Anticipation, overlap, arcs and staggered
   entrances (§7.1). This is the difference between "explainer quality" and
   "PowerPoint with figures".

---

## 2. Format and safe zones (vertical)

| Property      | Value                                   |
|---------------|-----------------------------------------|
| Canvas        | 1080 × 1920 (9:16)                      |
| Frame rate    | 30 fps, animated on ones (every frame), no stepped look |
| Rendering     | Vector with anti-aliasing; supersample 2× and downscale so thin shapes don't shimmer |
| Duration      | Follows the source clip (15–60 s)       |
| Audio         | Source clip audio is the narration; never re-time it (see §9 for the SFX bed) |

**Safe zones** (TikTok, Reels and Shorts UI all overlap the edges):

```
y=0    ┌──────────────────────────┐
       │  top UI, keep empty      │  0–220 px
y=220  ├──────────────────────────┤
       │                          │
       │   ACTION SAFE            │  x 60–940 (right 140 px = action buttons)
       │   main subject lives in  │
       │   y 380–1200             │
       │                          │
y=1300 ├──────────────────────────┤
       │  kinetic type / captions │  1300–1500
y=1500 ├──────────────────────────┤
       │  bottom UI, background   │  1500–1920 (username, description)
       │  only                    │
y=1920 └──────────────────────────┘
```

- The **subject** (character or main object) is centred horizontally, with its
  visual weight between y 380 and 1200.
- **Kinetic type** sits in its own band. It is either above the subject
  (y 260–420) or in the caption band (y 1300–1500), never on top of a face.
- The captions burned from the source take priority over the caption band.
  When captions are on, kinetic type moves to the top band.

---

## 3. Colour

### 3.1 Brand tokens (exact, from the brand stylesheet)

| Token            | Hex       | Brand variable        | Use                                              |
|------------------|-----------|-----------------------|--------------------------------------------------|
| `black`          | `#101010` | `brand-black`         | **Default stage background**; text on cream      |
| `surface`        | `#111111` | `aff-surface`         | Far background layer                             |
| `surface-raised` | `#131313` | `aff-surface-raised`  | Background shapes one step forward               |
| `overlay`        | `#1A1A1A` | `aff-overlay`         | Midground set pieces on black                    |
| `charcoal`       | `#2E2E2E` | `aff-map-state`       | Ground plane, map fills, furniture               |
| `cream`          | `#F5EEE5` | `brand-beige`         | Primary light: type, figures' lit side, inverted stage |
| `red`            | `#CB1414` | `brand-red` / red-600 | **Accent only**: key word, focal prop, the problem |
| `red-dark`       | `#A81111` | red-700               | Shadow side of red shapes                        |
| `red-deep`       | `#850E0E` | red-800               | Deepest red shadow; red-on-red layering          |

### 3.2 Value ramp (derived; cream over black)

The brand uses cream at reduced opacity over black for its mid-tones. For
animation we flatten those to solid fills, so overlapping shapes never show
through each other:

| Token      | Hex       | ≈ cream on black | Use                                              |
|------------|-----------|------------------|--------------------------------------------------|
| `tone-20`  | `#3E3C3B` | 20%              | Shadow side of dark clothing, distant crowd      |
| `tone-40`  | `#6C6965` | 40%              | Dark clothing, hair, background figures          |
| `tone-60`  | `#999590` | 60%              | Mid clothing, props, chart bars                  |
| `tone-80`  | `#C7C2BA` | 80%              | Skin shadow side, light clothing                 |
| `cream`    | `#F5EEE5` | 100%             | Skin lit side, shirts, paper, type               |

### 3.3 Data-only colours

Only for charts and maps where the narration names US political parties:
`dem` `#00AEF3` and `rep` `#E81B23` (the brand's own party tokens). They are
never used on characters, type or sets. In any other chart, the series the
narration is about is `red` and the rest are `tone-60`.

### 3.4 Rules

- **Black is home; cream is the reveal.** About 75% of shots use the `black`
  stage. The **inverted** stage (`cream` background, figures drawn in `black`
  and dark tones) is reserved for contrast beats ("but…", "the truth is…"), and
  the switch happens on a transition.
- **One red full-bleed per clip.** A single hard-hit beat (the key statistic,
  the punchline) may fill the frame with `red`, with type in `cream`. Never more than once.
- **Red budget:** ≤ 10% of the frame, and **one red focal element per shot.** If
  two things are red, one of them is wrong.
- **Figures must separate from the stage by value.** On `black`, nothing that
  matters is darker than `tone-40`; on `cream`, nothing that matters is lighter
  than `tone-60`.
- **No gradients** except the transparent black scrim (`#101010` at 70%) behind
  type over a busy set, matching the brand's image overlays. No glows, bevels or 3D.
- **One shadow tone per fill**: the next step down the ramp (cream →
  `tone-80`, red → `red-dark`). The light comes from the upper left, in every shot.
- Contrast: type must reach WCAG AA (4.5:1). `red` on `black` is only 3.3:1, so
  red type on black must be ≥ 96 px bold (large-text rule) or set as `cream`
  type on a solid red bar.

---

## 4. Typography

The brand typefaces are open source (Google Fonts):

| Role                  | Font             | Weight | Size @1080w | Case / setting                        |
|-----------------------|------------------|--------|-------------|---------------------------------------|
| Kinetic headline      | **Archivo**      | 700    | 96–128 px   | UPPERCASE, line-height 1.0, tracking 0 |
| Kinetic supporting    | Archivo          | 600    | 52–64 px    | UPPERCASE                             |
| Big numbers / stats   | Archivo          | 900    | 160–240 px  | Tabular figures                       |
| Kicker / label        | **Roboto Mono**  | 500    | 34–40 px    | UPPERCASE, tracking +4%, on a red underline bar |
| Quotes / body on card | Work Sans        | 500    | 48–56 px    | Sentence case                         |
| Document props        | Georgia-style serif (e.g. Source Serif 4) | 700 | 44–52 px | Only on paper/document props |

- **The brand kicker.** A short Roboto Mono label ("THE PROBLEM", "1971",
  "STEP 2") with a `red` rule under it, 6–8 px thick at 1080w (the brand's
  3–4 px heading underline, scaled). Use it to open a section or tag a chart.
- **At most two lines of 1–3 words each** per kinetic block. These are key
  words, not the transcript; the captions are the transcript.
- **The emphasis word is `red`; everything else is `cream`** on black (`black` on
  cream). On the red full-bleed beat, all type is `cream`.
- A **label bar**: a solid `red` (or `black` on cream) rectangle behind a word,
  padded 0.3em × 0.6em, **square corners**, like the brand's buttons. No
  rounded pills anywhere.
- Burned captions, when we control them: Archivo 700, `cream`, 6 px `black`
  stroke, and the active word in `red`.

---

## 5. Characters

### 5.1 Construction (target rig)

People are built from simple geometric parts so they can be rigged and posed:

| Part   | Shape                                                           |
|--------|-----------------------------------------------------------------|
| Head   | Rounded rectangle or egg, about 1/6 of total height (a slightly big head for phone legibility) |
| Eyes   | Two solid dots or short vertical ovals in `black`; no whites, no irises |
| Brows  | Short, thick strokes; **the main emotion carrier**              |
| Mouth  | Hidden when neutral. A small line, arc or open D-shape when talking or emoting |
| Nose   | Optional, a small wedge in the shadow tone                      |
| Body   | Torso as a tapered trapezoid; clothing *is* the body (suit, shirt, dress) |
| Limbs  | Tapered rounded strokes, about 0.35 of torso width; mitten or simple 3-finger hands |
| Feet   | Small rounded wedges, always touching the ground line           |

- Proportions: about 5.5 heads tall for adults, 4 for children.
- **Tonal colouring:** skin and light clothing are `cream`, with a `tone-80`
  shadow side. Dark clothing is `tone-40`/`tone-20`, and hair is `tone-40` or
  `tone-60`. On the cream stage, invert: skin is `tone-80` with a `tone-60`
  shadow, and dark clothing is `black`/`charcoal`. Variety comes from value,
  silhouette, hair and costume, not from hue.
- **Red on a character is a statement.** Only the focal figure of a shot may
  carry red (a tie, a sign, an armband), and only when the narration is about
  them.
- **No outlines** by default. If a figure must sit over a busy set, give the
  *whole group* a 6 px stroke in the stage colour, never per part.
- Characters are **types**, not portraits: worker, business owner, student,
  politician, judge, soldier, family, crowd. They are identified by costume and
  prop (hard hat, briefcase, gavel, graduation cap). **Real public figures are
  never drawn as recognisable caricatures.**

### 5.2 The stick-figure tier (interim)

Stick figures **cannot reach the target quality** on their own. Treat this tier
as the bridge to the full rig and close the gap with motion craft (§7.1),
sets and type:

- Line weight 14 px (at 1080w), with round caps and joins, in `cream` on black
  (`black` on cream).
- The head is a **filled** circle in the figure's colour, with two dot eyes in
  the stage colour, plus brows when emoting.
- **Value for role:** the protagonist is `cream`, bystanders and crowds are
  `tone-60`/`tone-40`, and the opposing or problem figure is `cream` with **one
  red element** (or fully `red` when the narration is about them).
- Each figure gets **one prop or costume shape** in flat tones (tie,
  briefcase, hard hat) so types read instantly.
- Every figure stands on the `charcoal` ground line (8 px) or casts a flat
  ellipse shadow (`black` at 40% on cream, or `surface` on black).

### 5.3 Poses and acting

- Keep a pose library, not free-form keyframes: `neutral`, `explain` (palm open
  toward the subject), `point`, `shrug`, `arms-crossed`, `thinking` (hand to
  chin), `celebrate` (arms up), `slump` (shoulders and head down), `walk`, `run`,
  `sit`, `present-to-chart`.
- Characters face 3/4 toward the centre of frame, or toward whatever they are
  reacting to. Use profile only for walking.
- **Idle never stops:** breathing (torso scale-Y 1.00↔1.015, period 3 s), a blink
  every 2.5–5 s (randomised, 3 frames closed), and a slight head bob on stressed
  syllables when the character is the speaker.
- **Lip-sync is minimal:** mouth open/closed driven by the audio amplitude
  envelope (threshold, plus a 2-frame minimum hold). No phoneme shapes.
- **Gestures land on stressed words.** A gesture's key pose hits on the word it
  emphasises (word timestamps from transcription).

---

## 6. Sets, props and infographics

### 6.1 Sets and depth

- Every set has **three parallax layers**:
  - **background** (`surface`/`surface-raised` shapes: skyline, columns, horizon)
  - **midground** (`overlay`/`charcoal`: ground plane, furniture, set props)
  - **subject**

  When the camera moves, background moves at 0.3×, midground at 0.6× and the
  subject at 1×. Parallax is what makes a flat set feel produced.
- Background shapes stay within 1–2 ramp steps of the stage, so they never
  compete with the subject.
- Settings are symbolic, not detailed: a "city" is 5–8 rectangle buildings with
  window grids, "government" is a columned facade and steps, a "factory" is a
  sawtooth roof and a chimney, and a "home" is a gable with a window.
- **Spotlight staging:** a soft-edged `charcoal` ellipse on the black floor under
  the subject, so the stage has a "lit" centre.

### 6.2 Visual-metaphor kit (reusable props)

Money stack, coin, price tag, bar chart, line chart, pie chart, scale of justice,
gavel, document/scroll, ballot box, megaphone, chain, padlock, key, ladder,
staircase, bridge, wall, door, maze, road fork, arrow (straight and curved),
lightbulb, clock, globe, map silhouette, flag, factory, house, school, hospital,
handshake, crowd silhouette.

**Each metaphor maps to a verb in the narration:** *rise* → ladder or up-arrow,
*block* → wall, *trap* → maze or chain, *choose* → road fork, *grow* → plant or
bar chart, *trade* → handshake or arrows between figures, *cost* → price tag,
*divide* → a line splitting two groups.

Props use the ramp. A prop turns **red** only when it is the shot's focal
element.

**Flags** are only shown when the narration names the country, and are drawn
in palette: stripes in `red`/`cream`, the canton in `charcoal` with `cream`
stars. They are never full-colour.

### 6.3 Data and infographics

- Bars, lines and pie slices are `tone-60` on black (`tone-40` on cream). The
  **one** series or bar the narration is about is `red`. Party charts use §3.3.
- Numbers **count up** from 0 (or the previous value) over 0.6–1.0 s with
  `ease-out`, landing exactly on the stressed syllable. Set them in Archivo 900.
- Axes are minimal: a `charcoal` baseline only, no gridlines, and Roboto Mono
  labels at 32–36 px.
- Maps: states/regions are `charcoal` (the brand's map token) with `tone-20`
  borders; highlighted regions are `red`.
- A chart is never shown without the narration referring to it. If the source
  gives no figure, **don't invent one**: use a metaphor.

---

## 7. Motion

### 7.1 Craft rules (what "quality" means here)

These separate broadcast explainer animation from cheap motion. Every shot must
use the ones that apply:

1. **Anticipation:** a 3–4 frame counter-move before any large move (a
   figure dips before jumping; an object pulls back 8 px before it flies).
2. **Overlap and follow-through:** parts lag the part that drives them
   by 2–3 frames (hand after forearm, tie after torso, the second line of type
   after the first) and settle with one small overshoot.
3. **Arcs:** limbs, thrown objects and camera travel move on curves, never
   straight lines between keys.
4. **Staggered entrances:** groups (bars, crowd members, icons, words)
   enter 2–3 frames apart, never all at once.
5. **Hold for reading:** any on-screen text stays fully visible for at least
   0.8 s + 0.25 s per word.
6. **Settle, don't stop:** every move ends in a slow drift or an idle cycle, never
   a dead freeze.
7. **No popping:** no element appears or disappears in a single frame (except on an
   intentional hard cut).

### 7.2 Easing (CSS cubic-bezier equivalents)

| Token         | Curve                               | Use                                    |
|---------------|-------------------------------------|----------------------------------------|
| `ease-std`    | `cubic-bezier(0.65, 0, 0.35, 1)`    | Camera moves, object moves             |
| `ease-out`    | `cubic-bezier(0.22, 1, 0.36, 1)`    | Entrances, count-ups                   |
| `ease-in`     | `cubic-bezier(0.64, 0, 0.78, 0)`    | Exits                                  |
| `pop`         | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Icons, labels, props appearing (~10% overshoot) |

Linear motion is only for continuous drifts (clouds, conveyor belts, the slow
camera push).

### 7.3 Timing

| Event                         | Duration           |
|-------------------------------|--------------------|
| Prop/icon pop-in              | 8–10 frames (`pop`) |
| Kinetic word in               | 6–8 frames, staggered 3 frames per word |
| Kicker underline draw-on      | 8 frames, left to right, `ease-out`, starting 2 frames after the label |
| Kinetic block out             | 6 frames (`ease-in`), 2–4 frames *before* the next block enters |
| Character pose change         | 6–10 frames, `ease-std`, 2-frame hold on the key pose |
| Shot length                   | **1.5–4 s** (avg ≈ 2.5 s); never > 5 s without a new element entering |
| Transition                    | 10–15 frames       |

### 7.4 Camera

- **Always moving.** Every shot has a slow push-in (scale 1.00 → 1.06 over the
  shot, linear) *or* a sideways truck (40–120 px over the shot), with parallax
  (§6.1).
- **Long-canvas travel:** for sequences ("first… then… finally…"), lay the scenes
  out on one tall canvas (vertical travel suits 9:16) and move the camera between
  them with `ease-std`.
- **Punch-in on emphasis:** on the sentence's key word, a quick 1.00 → 1.12 scale
  over 6 frames, then held.
- No camera shake, no rotation above 2°, no motion-blur trails.

### 7.5 Transitions (preferred order)

1. **Match/morph:** an object becomes the next scene's object (a coin becomes the
   globe, a bar becomes a building).
2. **Camera travel** along the long canvas.
3. **Red bar wipe:** a `red` rectangle with square edges sweeps across
   (`ease-std`), and the next scene is revealed behind it. Use it to switch
   between the black and cream stages. It is the signature transition, so use it
   at most three times per clip.
4. **Zoom-through:** push into a dark shape (a door or a pupil) to reveal the
   next scene.
5. A hard cut only on a dramatic beat (a sudden change or a punchline), at most
   twice per clip.

No cross-dissolves, spins, page curls or 3D flips.

---

## 8. Narration-to-picture rules (storyboarding)

These rules are what the **story** mode model must follow when it rewrites a clip.

1. **Segment by clause, not by sentence.** Split at commas, conjunctions and full
   stops. Each segment (about 1.5–4 s) is one shot.
2. **Each shot answers: "what is the literal picture of these words?"** Use this
   order of preference: a concrete character action, then a visual metaphor
   (§6.2), then an infographic (only with a real number), then kinetic type
   alone (the last resort, at most 20% of shots).
3. **One idea per shot.** At most one character action, plus one prop or one
   chart, plus one kinetic block, **plus exactly one red focal element.**
4. **Recurring cast.** At most three types per clip, visually consistent
   (same tones, costume and prop) for the whole clip.
5. **Hook first.** The first shot (0–2 s) is the strongest visual: a bold
   kinetic statement or the most dramatic metaphor. Never open on an empty
   establishing shot.
6. **Contrast beats.** "X… but Y" becomes the same composition twice with
   one element flipped (black stage to cream stage, tone to red, or growing to
   shrinking).
7. **Ending.** The final 1.5 s holds the clip's conclusion as a kinetic headline
   on the `black` stage, with the key word in `red` and a kicker above it. No
   logo, no end card.
8. **Faithfulness.** The pictures may simplify but must not add claims the speaker
   didn't make: no invented statistics, quotes, people or places.

### 8.1 Shot spec (what the model should emit per shot)

```json
{
  "start": 3.42,
  "end": 6.10,
  "narration": "and within ten years prices had doubled",
  "stage": "black",
  "camera": { "move": "push", "punch_on": "doubled" },
  "characters": [
    { "type": "shopper", "pose": "shrug", "position": "left", "accent": false }
  ],
  "props": [
    { "kind": "price_tag", "anim": "grow", "from": 1.0, "to": 2.0, "accent": true }
  ],
  "text": { "kicker": "1971–1981", "lines": ["PRICES", "DOUBLED"], "emphasis": "DOUBLED", "band": "top" },
  "transition_out": "morph"
}
```

- `stage` ∈ `black | cream | red`. The renderer derives all fills from the stage
  and the ramp, so the model never picks hex values.
- `accent: true` marks the shot's single red element. The renderer refuses (or
  drops the extras from) a shot with more than one.
- Every other field is drawn from a closed list (pose names, prop kinds,
  transition names), so the renderer never has to interpret free text.

---

## 9. Sound, texture and finish

- **SFX bed (optional, recommended):** a soft whoosh on transitions, a light
  tick or pop on icon entrances, and a low hit on the red full-bleed beat. Mix
  them ≥ 18 dB under the narration and never on top of a stressed word. No music
  unless the source has none.
- **Grain:** monochrome static noise at 2–3% opacity over the black stage, which
  keeps flat blacks from banding after platform recompression. No animated
  ("boiling") grain.
- Vignette: none, or at most 6% darker at the corners.
- Export: H.264 High, CRF ≤ 18, `-tune animation`, with `yuv420p` and a full-range
  tag checked, so `#101010` doesn't crush or lift.

---

## 10. Do / Don't

| Do                                                     | Don't                                               |
|--------------------------------------------------------|-----------------------------------------------------|
| Illustrate the exact words being said                  | Use generic "vibe" scenes                           |
| Build every frame from black, the cream ramp and red   | Introduce any other hue (outside party charts)      |
| One red focal point per shot                           | Red as decoration, or two red things competing      |
| Square corners on bars, labels and frames              | Rounded pills, soft cards, drop-shadow UI           |
| Key words on screen, 1–3 per line, Archivo uppercase   | Whole sentences on screen (that's captions)         |
| Parallax and constant gentle camera motion             | Flat, frozen frames > 0.5 s                         |
| Anticipation, overlap and staggered entrances          | Everything moving at once on the same curve         |
| Morph, camera-travel and red-wipe transitions          | Cross-dissolves, spins, flips                       |
| Types identified by props                              | Caricatures of real people                          |
| Flags in palette, only when the country is named       | Third-party logos, channel branding, end cards      |
| Numbers only when the speaker says them                | Invented statistics to fill a chart                 |
| Everything inside the safe zones                       | Faces or text under the platform UI                 |

---

## 11. Review checklist (per clip)

- [ ] Shot length is 1.5–4 s, and no shot > 5 s without a new element.
- [ ] Every shot's picture is the literal or metaphorical image of its words.
- [ ] Only palette tokens; exactly one red focal element per shot; at most one red
      full-bleed beat per clip.
- [ ] About 75% of shots on the black stage; the cream stage only on contrast beats.
- [ ] Figures separate from the stage by value (§3.4).
- [ ] Kinetic type: Archivo uppercase, ≤ 2 lines × 3 words, emphasis in red, inside
      its band, held long enough to read.
- [ ] Characters keep the same tones, costume and prop throughout; idle and blink running.
- [ ] The craft rules (§7.1) are visible: anticipation, overlap, arcs, staggers, no popping.
- [ ] Gestures, count-ups and punch-ins land on their stressed words (± 2 frames).
- [ ] Parallax camera motion in every shot; transitions from the allowed list.
- [ ] Opens on a hook visual and ends on the black-stage conclusion headline.
- [ ] Nothing important outside the safe zones; burned captions readable.
- [ ] No invented facts, no real-person caricatures, no third-party branding.
- [ ] No banding in the blacks after export.
