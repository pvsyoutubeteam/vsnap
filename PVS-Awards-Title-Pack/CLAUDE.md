# PVS Awards · chrome title pack

A generator for 3D award titles in one approved look: heavy, wide, polished-silver
letter faces with champagne-gold bevels and sides, on warm near-black. Any text
(A–Z, 0–9, punctuation) and any counter can be built, animated and rendered from a
small JSON file. Made for Matt and Chris at PVS Media for a one-minute black-tie
Christmas awards film, finished in Final Cut Pro.

You (Claude Code) are the operator. Matt describes a title in plain English; you
write or edit a shot file, render a draft, show him, and iterate.

## Ground rules

- **Draft first.** Always render `--quality draft` (640×360, about a second a frame)
  or stills before anything bigger. Matt reviews at draft or `review` (720p). Only
  render `master` / `uhd` when he asks for finals.
- **One shot = one JSON file in `shots/`.** Copy the nearest example; never edit
  `engine.py` to make a single shot work.
- **The look lives in `style.json`.** Do not change it for one shot (use the shot's
  `"style"` override) and do not change it at all without Matt asking: it is signed off.
- **Figures are placeholders** until Matt confirms them. Never invent a real KPI.
- Timings in shot files are **seconds on the shot's own timeline**; frame 1 is 0.0 s.
- After every render, tell Matt the paths of the movie and the cue sheet, and the
  time of each impact.

## Commands

    python3 make.py shots/sales.json                       # draft movie + cues
    python3 make.py shots/sales.json --stills hold         # one settled still (fastest check)
    python3 make.py shots/sales.json --stills 20,70,last   # stills at chosen frames
    python3 make.py shots/sales.json --quality review      # 1280×720
    python3 make.py shots/sales.json --quality master      # 1920×1080  (uhd = 3840×2160)
    python3 make.py shots/sales.json --alpha               # transparent background
    python3 make.py shots/a.json shots/b.json --quality review   # several + one FCP timeline

`make.py` finds Blender at `$BLENDER`, then `/Applications/Blender.app/Contents/MacOS/Blender`,
then `blender` on the PATH. It needs `ffmpeg` on the PATH to encode movies
(`brew install ffmpeg`); stills work without it. Rendering uses the GPU when Blender
has one available. A re-run resumes a part-finished render of the same settings;
`--fresh` forces a clean one.

First run on a new machine: `python3 make.py shots/sales.json --stills hold` and look
at the picture before doing anything else.

## What comes out (`out/<name>/`)

| File | Use |
|---|---|
| `<name>-<quality>.mp4` | Review copy, with a synthetic guide track (clicks on ticks, a hit on each impact) |
| `<name>-<quality>.mov` | For Final Cut. ProRes 422 HQ, silent. With `--alpha`: ProRes 4444, transparent |
| `<name>.fcpxml` | Import into Final Cut: the clip with a named marker on every cue |
| `cues.csv` / `cues.json` | Every cue with frame, seconds and timecode, for sound design |
| `<name>.blend` | The built scene, for looking around in Blender. Rebuilt every run; do not hand-edit |
| `out/timeline.fcpxml` | When several shots are rendered in one command: all of them end to end |

The `.fcpxml` points at the `.mov` by absolute path, so render on the machine you edit on.

## Sound design

Every shot reports **cues**: `in` (a move starts), `tick` (a digit flips or a letter
lands), `impact` (a line lands: where a hit or slam belongs), `sweep`, `hold`
(everything settled), `out`. They are in `cues.csv`, and as markers on the clip in
Final Cut (ticks are left out of the markers to keep the clip readable).

To move the picture to the music instead: change the `at` values so each impact falls
where the hit is, re-render the draft, check `cues.csv`. An impact lands at
`in.at + in.duration` (for a counter: `counter.at + counter.duration`), with durations
divided by `speed`.

The guide track in the `.mp4` is only a timing aid. The `.mov` is silent on purpose.

## Shot file

    {
      "name": "sales",                 // output folder and file names
      "fps": 25,                       // optional, default 25
      "speed": 1.0,                    // optional; 2.0 = every move takes half as long
      "duration": 6.0,                 // optional; default = last landing + 2.4 s hold
      "lines": [ ... ],                // top to bottom, centred as a stack
      "camera": { "move": "push_in" },
      "effects": { ... },
      "style": { ... }                 // optional per-shot overrides of style.json
    }

`speed` scales how long each move takes. It does not move the `at` start times.
The `//` notes above are explanation only; real JSON files cannot contain comments.

### Lines

    { "text": "SALES", "height": 0.72, "in": {...}, "out": {...}, "counter": {...}, "hero": false }

- `text`: upper-cased automatically. Any character in the font; see the alphabet proof.
- `height`: cap height in scene units. Defaults: 1.5 for a figure, 0.72 for a label.
  A line that would be wider than the frame is shrunk to fit, so long labels just work.
  For a two-line label use two lines.
- The biggest lines get the long studio highlight across their faces. Smaller lines
  read a little darker, which keeps the figure dominant.

### `in`: how a line arrives

| type | what happens | default duration |
|---|---|---|
| `turn` | whole line rotates in, gold edge first, lingering before the face arrives | 1.9 s |
| `slam` | drops from in front of the lens onto its mark with a small bounce | 0.32 s |
| `push` | arrives from deep in the set | 1.2 s |
| `flip` | each letter flips up in turn | 0.3 s per letter |
| `rise` | each letter rises and tips into place | 0.5 s per letter |
| `drop` | each letter falls into place with a small bounce | 0.42 s per letter |
| `cut` | simply there | – |

    "in": { "type": "rise", "at": 0.2, "duration": 0.5, "stagger": 0.05 }

`stagger` is the delay between letters (per-letter types only). A line with a counter
can use `turn`, `slam`, `push` or `cut`.

### `counter`: for a line whose text contains a number

    "counter": { "mode": "flip", "at": 1.88, "duration": 1.68 }

- `flip`: each position flips through two decoy digits onto the real one, left to right.
- `count`: counts up from zero and eases into the final figure, with a small pop on landing.

Commas, decimals and symbols are kept: `1,248`, `98.5%`, `£4.2M`, `+312`. Digits sit in
equal-width slots so nothing jitters; add `"tabular": false` to the line for natural
spacing with `flip`.

### `out`: optional exit

    "out": { "type": "push", "at": 4.6, "duration": 0.5 }

`turn` (rotates away), `push` (flies past the lens), `drop` (falls out of frame), `cut`.

### Camera

`"move"`: `push_in` (slow push, the default), `pull_back`, `static`, or `reveal`
(starts tight on the first line's gold edge and opens out to the full frame as it lands).
`"lens"`: focal length in mm, default 55. The camera always stays centred.

### Effects

    "effects": {
      "sweep": true,            // travelling softbox; or { "at": 1.4, "duration": 2.4 }; false = off
      "glint": true,            // the long highlight flares as each big line lands
      "shake": 0.5,             // camera shake on each impact, 0 = none, 1 = hard
      "dof": false,             // soft focus at the start, crisp by the first landing
      "motion_blur": false,     // good with slam / push; slower to render
      "bloom": 0.35,            // glow on bright areas (0 = off)
      "streak": 0.5             // warm anamorphic streak on the brightest glints (0 = off)
    }

`bloom` and `streak` are added when the movie is encoded, so changing them does not
need a re-render of the frames. They are skipped for `--alpha` output, where glow
belongs in Final Cut.

### Style (`style.json`, or `"style"` in a shot)

`font` (any .ttf/.otf path; the bundled Archivo Black Expanded is an open-licence
stand-in until Matt picks a licensed face), `x_scale`, `tracking`, `extrude` (depth),
`bevel`, `line_gap`, `max_width`, `silver`, `gold`, `face_roughness`,
`gold_roughness`, `background`, `silk_strength`, `band_strength`, `band_width`,
`band_height`, `gold_bounce`, `practicals` (number of bokeh lights; 0 = none).

Changing the font changes every width, so re-check the alphabet proof and the longest
label (`INSTRUCTIONS`, `COUNTRIES LAUNCHED IN`) afterwards.

## Examples in `shots/`

| File | Shows |
|---|---|
| `sales.json` | The approved shot: `turn` label, `flip` counter, `reveal` camera |
| `exchanges.json` | `rise` label, `count` counter |
| `countries.json` | Two-line label with `drop`, `count`, soft-focus start, `pull_back` |
| `instructions.json` | Longest label with `flip` cascade, `push` figure, `turn` exit, 1.4× speed |
| `awards-night.json` | Hero title: two `slam`s, hard shake, motion blur, `push` exit |
| `alphabet.json` | Character-set proof; render with `--stills last` |

## How the look works (read before touching `engine.py`)

- Each glyph is a mesh with two materials: gold on bevel and sides, silver on the
  front face. The front face is flat-shaded so it behaves as a true mirror.
- The silver shows what is behind the camera: a graded "silk" card and one long strip
  card per big line. That strip is the clean highlight across the figure. Cards are
  hidden from the camera and only exist as reflections.
- A mirror face at the origin sees the card plane magnified by
  (card distance + camera distance) / camera distance, which is how the strip is
  placed to land on the upper part of the letters.
- `face_roughness` must stay very low (about 0.015). The cards are far away, so even
  0.07 smears the highlight into grey.
- Area lights also show in the mirror. Keep them outside the area the faces reflect,
  or they leave bright patches on the settled frame.
- `engine.py` is written for the Blender 4.3 Python API and was run on Blender 5.3
  when this pack was made. If a call fails on your version, fix that call only.

## Still to decide with Matt

Final typeface, the real figures, venue aspect ratio / resolution / frame rate, the
music, and the dedication card.
