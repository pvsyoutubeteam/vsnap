# PVS Media · Christmas awards titles

Matt and Chris are making a one-minute cinema-trailer-style celebration for a UK estate and letting agency audience at a black-tie Christmas party. This folder is a working Blender prototype for the Mac and Final Cut Pro. The immediate creative decision is how the metal and the first counter should look and move. SALES and 1,248 are test copy. All real KPI figures, logos, the venue raster and final music are pending.

## First session

1. Open review/sales-proof.mp4 and review/hero-0110.png. Compare them with assets/material-options.png. The fifth row (polished silver face with a champagne-gold bevel and sides) is the starting direction for discussion. The reference is a concept still. The Blender render is the actual prototype.
2. Locate the existing Blender binary and print its version. On macOS the standard installation is /Applications/Blender.app/Contents/MacOS/Blender. The scene was built on Blender 4.3.2. Check FFmpeg availability for movie exports. Blender and the packaged clip can be opened independently of FFmpeg. Use local tools; no cloud render account or API key is needed.
3. Create a versioned working copy of this folder, e.g. ../PVS-Awards-Type-v02. Edit and run the builder from that copy. The build script recreates AwardsType.blend from shot.json and writes beside the script. Manual Blender changes belong in a separately saved scene.
4. Render three new v02 test stills around frames 20, 70 and 110. Improve the chrome reflections, edge separation and counter rhythm first. Compare the settled frame at thumbnail size. Keep label and numbers centred, and protect the comma and side bearings. Export one revised six-second movie with the supplied timing track. Give Matt the local file paths and a short account of changes.

## What the scene contains

A procedural two-material title builder, replaceable font, fixed-width digit slots, sequential digit flips, a travelling softbox, a centred camera, warm practicals and timing markers. It works with uppercase labels and numbers; the display-value field also accepts common symbols listed in build.py. Sizes and positions are tuned for the supplied SALES test. Compare the longest planned label before generalising the layout. The starting font is a bundled DejaVu Sans Bold proxy. Choose a wider, heavier geometric face with Matt and keep the font path configurable. A stylised horizontal reflection is built into the prototype silver shader; refine the studio reflections for the final finish. The WAV is an original synthetic timing guide for the edit.

## Local commands (Terminal, from the working copy)

    BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
    "$BLENDER" -b --python-exit-code 1 -P build.py
    "$BLENDER" -b AwardsType.blend -o "$PWD/review/test-" -F PNG -f 20,70,110

For a 960 × 540 draft from the saved scene, render frames 1–150 to PNG. This can be resumed using -s and -e for the required frame range. The project base is 1920 × 1080, set to 50% in the scene. The packaged viewing copy is 768 × 432 at 25 fps.

    mkdir -p frames
    "$BLENDER" -b AwardsType.blend -o "$PWD/frames/sales-" -F PNG -a
    ffmpeg -n -framerate 25 -start_number 1 -i frames/sales-%04d.png -i review/timing-track.wav -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac -b:a 192k -movflags +faststart review/sales-v02.mp4

For a picture-and-audio editing copy in Final Cut from those same frames:

    ffmpeg -n -framerate 25 -start_number 1 -i frames/sales-%04d.png -i review/timing-track.wav -c:v prores_ks -profile:v 2 -pix_fmt yuv422p10le -c:a pcm_s24le review/sales-v02.mov

The scene includes the opaque studio background. The ProRes export uses the rendered frame dimensions. Confirm venue aspect ratio, resolution, frame rate and playback spec before mastering. Re-render at the target raster before the final encode.

## Creative direction

Begin in warm near-black, with a glint along a deep gold bevel. Let the turn towards camera reveal a heavy, wide silver letterface. Use a small amount of shallow focus or haze at the reveal, then resolve to a crisp readable KPI. Restrict the strongest anamorphic glint to the main accent. Aim for Christmas warmth from practical lights and champagne reflections. The motion can become fast and intense between KPI holds.

Frames 1–47 introduce the label. Frames 48–90 resolve the figure. Frames 91–150 leave a readable hold. Keep the direction flexible while Matt reviews the proof. A key-in-lock sound folding into a low orchestral hit is a sound-design idea for the final mix.

## After sign-off

Build a reusable title generator for A–Z, 0–9 and required punctuation using the approved face and material controls. Support manual final figures, comma grouping and readable label layouts. Test INSTRUCTIONS, SALES, EXCHANGES and COUNTRIES LAUNCHED IN at actual venue size. Offer a centred two-line label where needed. Keep counters, camera, lights and render paths per shot configurable. Assemble the minute in Final Cut so the edit can follow the actual music. Confirm the figures and final dedication with Matt.
