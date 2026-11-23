# Chrome titles

Liquid-chrome 3D title cards, rendered offline and delivered as layers for Final Cut Pro.

## What you get (`out/`)

| File | What it is |
|---|---|
| `title_01.mov` … `title_04.mov` | One clip per card: clean chrome lettering, ProRes 4444 **with alpha** |
| `title_01_flare.mov` … | That card's bloom and anamorphic flare on its own, ProRes 4444 with alpha |
| `background.mov` | 40 s bokeh / haze plate, ProRes 422 HQ |
| `ChromeTitles.fcpxml` | FCP timeline: background in the primary storyline, titles on lane 1, flares on lane 2 |
| `preview.mp4` | Flattened preview of the whole timeline |

In Final Cut: **File ▸ Import ▸ XML…** and pick `ChromeTitles.fcpxml`. The XML points at the
`.mov` files by absolute path, so render on the Mac you edit on, or if the clips were rendered
elsewhere run `node render.mjs fcpxml --media /path/to/folder/with/the/movs` to rewrite it
(or relink when FCP asks).

The flare clips carry their brightness as alpha, so they sit correctly with the default
**Normal** blend; lower a flare clip's opacity to dial it back, switch it to **Add** for a hotter
glint, or disable it for bare chrome.
Each card is its own clip, so you can slide, trim, retime, scale, colour-correct or swap the
background without re-rendering.

## Rendering

Needs Node, ffmpeg, and Playwright with Chromium.

```
npm install
node render.mjs sheet --scale 0.5        # contact sheet of every card  -> out/stills/
node render.mjs still --card 4 --t 7.6   # one full-res frame
node render.mjs render                   # everything (4K: roughly 4 s per frame on a 4-core CPU)
node render.mjs render --scale 0.5       # quick half-size draft
node render.mjs render --only title_04   # re-render one card (or: --only bg)
```

Live look in a browser: serve this folder and open `scene.html?preview`.

## Changing things (`config.json`)

- **Words / timing** – `cards[]`: `lines` (one string per line, caps), `start`, `duration` (seconds),
  `sweep` and `flare` strength, `hero: true` for the big double-sweep finish.
- **Typeface** – `font`: any `.ttf`/`.otf` path. Drop a licensed Monument Extended, Druk Wide or
  Akira Expanded file into `fonts/` and point at it. Bundled open-licence stand-ins:
  `Archivo-BlackExpanded.ttf` (default) and `Unbounded-Black.ttf`.
- **Letterforms** – `type`: `tracking`, `depth` (extrusion), `bevel`, `bevelSegments` (1 = hard chamfer).
- **Look** – `look`: `gold` / `white` light colours, `liquid` (reflection wobble), `edgeGlass`,
  `bloom`, `flare`, `flareThreshold`, `flareTint`, `bokeh`, `haze`, `exposure`.
- **Camera** – `camera`: push-in distances, tilt and swing.
- **Format** – `output`: size, fps, total duration.

The studio reflected in the chrome (horizon, softboxes, sweep light) is the `env()` function in
`scene.js`; the entry/exit animation is in `drawFrame()`.
