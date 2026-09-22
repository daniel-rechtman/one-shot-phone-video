---
name: one-shot-phone-video
description: Daniel's house style for AI short-form video that must read as REAL phone footage — vertical 9:16, one continuous handheld take, amateur framing, natural ambient audio, no music. Runs on fal.ai through the local CLI at ~/קלודקוד/seedance, with MiniMax H3 as the default engine (5-17x cheaper than Seedance 2.0 for the same job) and character identity locked from a character sheet. Use whenever Daniel asks for a short AI video clip that should look filmed on a phone — "סרטון שנראה מצולם מהטלפון", "שוט אחד", "צילום מפלפון", "תעשה סרטון של X עושה Y", "רילס", "טרנד", "UGC", "phone-shot", "one shot", "handheld", or names a trend format (פתיחת סתימות, הרכבת רהיטים, בדיקת מוצר, prank, POV). Trigger even when he only describes the scene and does not say "phone" — one-shot phone realism is the default for these. Also use when he wants a recurring character kept consistent across clips, or asks what a clip will cost before generating.
---

# one-shot-phone-video

Short AI clips that pass as real phone footage. Converged over real runs on 2026-09-22.

## The tool

`~/קלודקוד/seedance/seedance.py` — stdlib-only CLI, no deps. Read its README first.

```bash
cd ~/קלודקוד/seedance
./seedance.py ref "<prompt>" -i characters/<name>.jpg --engine h3 --dur 15 --res 2k --ar 9:16 --seed <n>
```

Key is in `~/.claude/secrets/fal.json`. Every run is logged to `runs/ledger.jsonl`;
`./seedance.py spend` totals it.

## Engine: H3 by default

| | Seedance 2.0 | **MiniMax H3** |
|---|---|---|
| pricing | per token, quadratic in resolution | **flat per second** |
| 15s at 2K | — | **$1.95** |
| 15s at 4K | ~$40 | **$2.40** |
| references | 12 files | 12 files (first 5 images free) |

Same multi-reference capability, a fraction of the price. Use `--engine seedance` only
to A/B a shot where H3's output disappoints. **2K is the sweet spot** — Daniel asked to
drop from 4K and the difference is invisible on a phone.

## Write a shot script, not a description

The prompt is a **shooting script**. Describing what happens produces props that teleport
and a camera that has no opinion. Every beat gets three lines — **SHOT, ACTION, SOUND** —
and everything is decided before a single call is made.

Header block first, then the beats:

```
FORMAT: Vertical 9:16 smartphone video. One continuous handheld take, no cuts.
Amateur operator - the frame drifts and re-centers, and the operator physically
steps closer instead of zooming. No music. 15 seconds.

CHARACTER (locked to Image 1): <identity anchors, restated verbatim>
WARDROBE: <every garment, and its condition>
LOCATION: <the room and its mess>
LIGHT: <source, hardness, what stays dark>

0:00-0:01.5 HOOK
SHOT:   <framing, camera distance, angle, movement>
ACTION: <exactly what happens, in order>
SOUND:  <specific diegetic sounds>

0:01.5-0:05 REVEAL
SHOT:   ...
ACTION: ...
SOUND:  ...

<one beat per section, named for its job>

CONTINUITY: <what must not drift between beats>
```

### SHOT — give the camera a job every beat

An amateur operator is a *character*. Write their behaviour: **steps closer instead of
zooming**, loses focus and recovers, whips the phone down to follow something, crouches,
tilts up. A beat whose SHOT line is missing is a beat the model will frame blandly.

Make the last shot **the reverse of the hook's shot** when you can — tilting back up to
the thing that was overflowing closes the loop visually, not just narratively.

### ACTION — every object enters in someone's hands

The failure that cost a re-run: "she grabs a beer" produced a bottle materializing on a
windowsill. The fix: *"the bald toddler waddles back in holding a brown glass bottle and
holds it out to her — the handoff is clearly visible on camera."* If a prop matters,
film it arriving.

Write reactions too, especially the withheld ones — *"she does not flinch"*, *"deadpan,
never acknowledging the camera"*. The comedy is that nobody in frame thinks it is funny.

### SOUND — name the sounds, and say no music

List the specific diegetic sounds per beat: the squeak, the slop, the wet slap, the rush.
**Always "No music."** Music is the fastest tell that a clip was produced rather than filmed.

### CONTINUITY — the last line

State what must not drift: the locked face, a garment that stays on, a prop that holds its
position in frame. Without it, gloves vanish between beats and the character's face slides.

## The hook — first 1.5 seconds

**Never open on an establishing shot.** The opening frame carries the most extreme image
in the clip, and the viewer arrives late to something already going wrong.

"Extreme but real" is the constraint Daniel set, and it is the whole craft:

- **Extreme** = the worst moment of the situation, not a preview of it. Not a clogged
  sink — a sink already overflowing black water onto the floor.
- **Real** = something a phone could actually have caught. Overflow, spray, a mess in
  progress, a hand already deep in it. Never physics-breaking stunts, never anything that
  reads as a rendered effect. **The absurdity is the character, not the event.**

Hold the reveal for beat two. The toddler lands harder once the mess has already grabbed
the viewer. The hook is a promise — the final beat must pay it off.

### Length

**15 seconds is the floor for three or more beats.** 10s compressed a 3-beat scene and cut
the punchline. Only use 5-10s for a single action.

A full worked script, with a breakdown of why each beat is built the way it is, lives in
`references/worked-script.md`. Start from its skeleton: **hook, reveal, escalation, money
shot, payoff.** That arc ports to any trend format.

## Character consistency

`characters/<name>.jpg` holds a **character sheet** — one image, multiple angles and
expressions. One sheet beats several separate photos: it locks identity better and counts
as a single reference, so it stays inside the 5 free images.

Cite it in the prompt as `Image 1` for H3 (`@Image1` for Seedance) and restate the
identity anchors every time: *"the chubby toddler girl from Image 1 — identical face,
same two pigtails with pink hair ties"*. Wardrobe can change; face and hair must be
re-stated verbatim across clips or the character drifts.

## House style, non-negotiable

- Vertical 9:16, `--ar 9:16`
- "one continuous take" in the prompt — no cuts, no camera moves that imply editing
- "slightly shaky", "amateur framing", "shot on iPhone"
- **Natural ambient audio, explicitly listed. Always "No music."** Music is the single
  fastest tell that a clip is produced rather than filmed.
- Deadpan performance. The joke is that nobody in frame thinks it is a joke.

## Trend formats

Match the genre's actual grammar, not just its subject. For drain-unclogging: tight
shaky close-up, a long slow pull on the clog, the wet slap, and the satisfying rush of
clean water at the end. Research the format's beats before writing if unfamiliar.

## Delivery

Output lands in `runs/<ts>-ref/`. The 2K master is 25-40MB — **over the 30MiB limit for
phone/web delivery**, so always also produce a shareable 1080p:

```bash
ffmpeg -y -i <master>.mp4 -vf "scale=1080:-2" -c:v libx264 -preset slow -crf 24 \
  -c:a aac -b:a 128k <name>-1080p.mp4
```

Send the 1080p; say the master is on disk.

## Traps already hit and fixed

- **Cost by engine.** H3 is flat per second; applying Seedance's token formula to an H3
  clip reported $27.85 for a $1.62 job. `price_ctx` carries the pricing model through.
- **Resolution scales differ.** H3 is `480P/768P/2K/4K`; Seedance is `480p/720p/1080p/4k`.
  The CLI maps and rejects mismatches.
- **fal returns bigger dimensions than requested** (asked 480p, got 496x864), so the
  pre-estimate carries a 10% margin and is a ceiling. Real cost is measured from the MP4.
- **Exhausted balance** returns HTTP 403 `User is locked`. Nothing is charged. Daniel
  tops up at fal.ai/dashboard/billing — never do this for him.
- **Uploads can 403 while the account is locked** and silently fall back to a data URI.
  If a run succeeds right after a top-up, that is why.
- A submitted job keeps running and **is billed** even if the CLI is interrupted.
  Recover with `./seedance.py get <request_id>`, never re-run.

## Before generating

State the cost. `--dry-run` shows the payload and price without spending. Anything over
$2.50 prompts for confirmation — do not pass `-y` on Daniel's behalf without asking.
