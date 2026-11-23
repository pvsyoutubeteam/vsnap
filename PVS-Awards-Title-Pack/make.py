#!/usr/bin/env python3
"""Build, render and package award title shots.  Standard library only.

    python3 make.py shots/sales.json                      draft movie (640x360, fast)
    python3 make.py shots/sales.json --quality review     1280x720
    python3 make.py shots/sales.json --quality master     1920x1080   (uhd = 3840x2160)
    python3 make.py shots/sales.json --stills hold,20,70  stills only, no movie
    python3 make.py shots/sales.json --alpha              transparent background, ProRes 4444
    python3 make.py shots/*.json --quality review         several shots + one FCP timeline

Per shot, in out/<name>/:  <name>-<quality>.mp4 (review copy with guide audio),
<name>-<quality>.mov (ProRes for Final Cut, silent), cues.json / cues.csv,
<name>.fcpxml (the clip with a marker on every cue), <name>.blend.
"""
import argparse
import array
import csv
import json
import math
import os
import random
import shutil
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def find_blender():
    for c in (os.environ.get("BLENDER"), "/Applications/Blender.app/Contents/MacOS/Blender", shutil.which("blender")):
        if c and Path(c).exists():
            return [c, "-b", "--python-exit-code", "1", "-P"]
    try:                                  # Blender installed as a Python module (pip install bpy)
        subprocess.run([sys.executable, "-c", "import bpy"], check=True, capture_output=True)
        return [sys.executable]
    except Exception:
        sys.exit("Blender not found. Install it, or set BLENDER=/path/to/blender")

def tc(frame, fps):
    n = frame - 1
    return f"{n // fps // 60:02d}:{n // fps % 60:02d}:{n % fps:02d}"

def guide_audio(info, path):
    """A synthetic timing guide: a click on every tick, a low hit on every impact."""
    rate, fps = 48000, info["fps"]
    secs = info["frames"] / fps
    ticks = [c["seconds"] for c in info["cues"] if c["type"] == "tick"]
    hits = [c["seconds"] for c in info["cues"] if c["type"] == "impact"]
    rng, low = random.Random(77), 0.0
    samples = array.array("h")
    for n in range(int(rate * secs)):
        t = n / rate
        noise = rng.uniform(-1, 1)
        low += .04 * (noise - low)
        v = .03 * math.sin(2 * math.pi * 44 * t) * min(1, t / 1.2)
        for b in ticks:
            dt = t - b
            if 0 <= dt < .2:
                v += .15 * math.exp(-dt * 80) * (noise * .45 + math.sin(2 * math.pi * 1340 * dt) * .55)
        for h in hits:
            dt = t - h
            if -.9 < dt < 0:              # short riser into the hit
                p = 1 + dt / .9
                v += p * p * .10 * low
            if dt >= 0:
                v += .5 * math.exp(-dt * 3.3) * math.sin(2 * math.pi * (47 * dt + 2.2 * (1 - math.exp(-dt * 22))))
                v += .22 * math.exp(-dt * 10) * low
        samples.append(round(32767 * max(-.95, min(.95, v)) * min(1, (secs - t) / .15)))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as f:
        f.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        f.writeframes(samples.tobytes())

def glow_filter(fx, h):
    """Bloom and a warm anamorphic streak on the brightest glints, done in ffmpeg."""
    bloom, streak = float(fx.get("bloom", .35)), float(fx.get("streak", .5))
    if bloom <= 0 and streak <= 0:
        return None
    k = h / 720
    lut = lambda lo, gain: "lutrgb=" + ":".join(f"{c}='clip((val-{lo})*{gain:.3f},0,255)'" for c in "rgb")
    return (f"format=gbrp,split=3[a][b][c];"
            f"[b]{lut(205, 5.1 * bloom)},gblur=sigma={9 * k:.1f}[bl];"
            f"[c]{lut(232, 11 * streak)},gblur=sigma={70 * k:.1f}:sigmaV={1.6 * k:.1f},"
            f"colorchannelmixer=rr=1:gg=.84:bb=.6[st];"
            f"[a][bl]blend=all_mode=screen[ab];[ab][st]blend=all_mode=screen")

def fcpxml(clips, path, name):
    """clips: [(info, mov path)] laid end to end, each with a marker per cue."""
    first = clips[0][0]
    fps, w, h = first["fps"], first["width"], first["height"]
    T = lambda frames: f"{int(frames) * 100}/{fps * 100}s"
    esc = lambda s: s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    std = {(1920, 1080): f"FFVideoFormat1080p{fps}", (1280, 720): f"FFVideoFormat720p{fps}",
           (3840, 2160): f"FFVideoFormat3840x2160p{fps}"}.get((w, h))
    assets, spine, offset = [], [], 0
    for i, (info, mov) in enumerate(clips):
        rid = f"r{i + 2}"
        assets.append(f'    <asset id="{rid}" name="{esc(info["name"])}" start="0s" duration="{T(info["frames"])}" hasVideo="1" format="r1" videoSources="1">\n'
                      f'      <media-rep kind="original-media" src="{Path(mov).resolve().as_uri()}"/>\n    </asset>')
        marks = "".join(f'\n              <marker start="{T(c["frame"] - 1)}" duration="{T(1)}" value="{esc(c["type"].upper() + " – " + c["label"])}"/>'
                        for c in info["cues"] if c["type"] != "tick")
        spine.append(f'            <asset-clip ref="{rid}" offset="{T(offset)}" name="{esc(info["name"])}" start="0s" duration="{T(info["frames"])}" format="r1" tcFormat="NDF">{marks}\n            </asset-clip>')
        offset += info["frames"]
    path.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    <format id="r1"{f' name="{std}"' if std else ''} frameDuration="{T(1)}" width="{w}" height="{h}" colorSpace="1-1-1 (Rec. 709)"/>
{chr(10).join(assets)}
  </resources>
  <library>
    <event name="PVS Awards Titles">
      <project name="{esc(name)}">
        <sequence format="r1" duration="{T(offset)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>
{chr(10).join(spine)}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
''')

def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode:
        sys.exit(f"FAILED: {' '.join(map(str, cmd))}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shots", nargs="+")
    ap.add_argument("--quality", default="draft", choices=["draft", "review", "master", "uhd"])
    ap.add_argument("--stills", default="", help="comma list of frames, or 'hold' / 'last'; skips the movie")
    ap.add_argument("--alpha", action="store_true", help="transparent background, ProRes 4444, no glow pass")
    ap.add_argument("--fresh", action="store_true", help="delete previously rendered frames first")
    a = ap.parse_args()
    blender, done = find_blender(), []
    for shot in a.shots:
        name = json.loads(Path(shot).read_text()).get("name", Path(shot).stem)
        out = ROOT / "out" / name
        frames = out / "frames"
        # frames are only reusable for the same shot settings, quality and alpha
        stamp = json.dumps([Path(shot).read_text(), (ROOT / "style.json").read_text(), a.quality, a.alpha])
        if frames.exists() and (a.fresh or not (out / "stamp").exists() or (out / "stamp").read_text() != stamp):
            shutil.rmtree(frames)
        cmd = blender + [str(ROOT / "engine.py"), "--", str(shot), "--quality", a.quality]
        cmd += ["--stills", a.stills] if a.stills else ["--anim"]
        cmd += ["--alpha"] if a.alpha else []
        out.mkdir(parents=True, exist_ok=True)
        if not a.stills:
            (out / "stamp").write_text(stamp)
        run(cmd)
        info = json.loads((out / "cues.json").read_text())
        fps = info["fps"]
        with open(out / "cues.csv", "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["type", "frame", "seconds", "timecode", "label"])
            for c in info["cues"]:
                wr.writerow([c["type"], c["frame"], c["seconds"], tc(c["frame"], fps), c["label"]])
        if a.stills:
            print(f"stills -> {out}")
            continue
        if not shutil.which("ffmpeg"):
            sys.exit(f"Frames are in {frames}; install ffmpeg to encode movies.")
        fx = json.loads(Path(shot).read_text()).get("effects", {})
        vf = None if a.alpha else glow_filter(fx, info["height"])
        src = ["-framerate", str(fps), "-start_number", "1", "-i", str(frames / "f-%04d.png")]
        tag = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
        ff = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        mov, mp4, wav = out / f"{name}-{a.quality}.mov", out / f"{name}-{a.quality}.mp4", out / "guide-audio.wav"
        guide_audio(info, wav)
        if a.alpha:
            run(ff + src + ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0"] + tag + [str(mov)])
            run(ff + ["-f", "lavfi", "-i", f"color=c=0x1a1c22:s={info['width']}x{info['height']}:r={fps}"] + src + ["-i", str(wav),
                      "-filter_complex", "[0][1]overlay=shortest=1,format=yuv420p", "-map", "2:a", "-c:v", "libx264", "-crf", "18",
                      "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(mp4)])
        else:
            chain = (vf + "," if vf else "")
            run(ff + src + ["-vf", chain + "format=yuv422p10le", "-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0"] + tag + [str(mov)])
            run(ff + src + ["-i", str(wav), "-vf", chain + "format=yuv420p", "-c:v", "libx264", "-crf", "18",
                            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart"] + tag + [str(mp4)])
        fcpxml([(info, mov)], out / f"{name}.fcpxml", name)
        done.append((info, mov))
        print(f"movie  -> {mp4}\nprores -> {mov}\ncues   -> {out / 'cues.csv'}\nfcp    -> {out / (name + '.fcpxml')}")
    if len(done) > 1:
        fcpxml(done, ROOT / "out" / "timeline.fcpxml", "PVS Awards Titles")
        print(f"timeline -> {ROOT / 'out' / 'timeline.fcpxml'}")

if __name__ == "__main__":
    main()
