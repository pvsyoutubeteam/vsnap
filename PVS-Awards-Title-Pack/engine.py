"""PVS awards title engine. Runs inside Blender; use make.py to drive it.

    blender -b --python-exit-code 1 -P engine.py -- shots/sales.json --quality draft --anim

Builds one shot (a stack of chrome text / counter lines) from a JSON file plus
style.json, saves the .blend, renders stills or the frame sequence, and writes
cues.json (frames where things land) for sound design.
Written against the Blender 4.3 Python API; also runs on 5.x.
"""
import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("shot")
ap.add_argument("--quality", default="draft")
ap.add_argument("--stills", default="")
ap.add_argument("--anim", action="store_true")
ap.add_argument("--alpha", action="store_true")
ap.add_argument("--out", default="")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

QUALITY = {  # width, height, samples
    "draft": (640, 360, 20), "review": (1280, 720, 64),
    "master": (1920, 1080, 128), "uhd": (3840, 2160, 128),
}
shot_path = Path(args.shot).resolve()
shot = json.loads(shot_path.read_text())
S = json.loads((ROOT / "style.json").read_text())
S.update(shot.get("style", {}))
FX = {"sweep": True, "glint": True, "shake": 0.0, "dof": False, "motion_blur": False}
FX.update(shot.get("effects", {}))
NAME = shot.get("name", shot_path.stem)
OUT = Path(args.out).resolve() if args.out else ROOT / "out" / NAME
OUT.mkdir(parents=True, exist_ok=True)
FPS = int(shot.get("fps", 25))
SPEED = float(shot.get("speed", 1.0))
rng = random.Random(shot.get("seed", 42))

def F(seconds):
    """Timeline seconds -> frame number (frame 1 is time zero)."""
    return int(round(seconds * FPS)) + 1

def D(seconds):
    """An animation duration in seconds -> frames, scaled by the shot speed."""
    return max(1, int(round(seconds * FPS / SPEED)))

# ------------------------------------------------------------------ scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
W, H, SAMPLES = QUALITY[args.quality]
scene.render.engine = "CYCLES"
scene.cycles.samples = SAMPLES
try:
    scene.cycles.use_denoising = args.quality == "draft"
except Exception:
    pass
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.render.film_transparent = args.alpha
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA" if args.alpha else "RGB"
scene.render.use_motion_blur = bool(FX["motion_blur"])
try:  # use the GPU when Blender has one configured (Metal on Apple silicon)
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("METAL", "OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
        except Exception:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == kind]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == kind
            scene.cycles.device = "GPU"
            break
except Exception:
    pass

world = bpy.data.worlds.new("Black studio")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (*S["background"], 1)

def metal(name, color, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Metallic"].default_value = 1
    bs.inputs["Roughness"].default_value = roughness
    return mat

GOLD = metal("Champagne • bevel and sides", S["gold"], S["gold_roughness"])
SILVER = metal("Polished silver • face", S["silver"], S["face_roughness"])
font = bpy.data.fonts.load(str(ROOT / S["font"]))
font.pack()

def key(obj, prop, frame, value):
    setattr(obj, prop, value)
    obj.keyframe_insert(data_path=prop, frame=frame)

def show(obj, on, off=None):
    """Visible from frame `on` (None = from the start) until frame `off`."""
    for prop in ("hide_render", "hide_viewport"):
        if on is not None and on > 1:
            key(obj, prop, 1, True)
            key(obj, prop, on, False)
        if off is not None:
            if on is None or on <= 1:
                key(obj, prop, 1, False)
            key(obj, prop, off, True)

# ------------------------------------------------------------------ glyphs
def curve_mesh(body, solid=True):
    curve = bpy.data.curves.new("tmp", "FONT")
    curve.body, curve.font = body, font
    curve.space_character = S["tracking"]
    curve.resolution_u = 12
    if solid:
        curve.extrude, curve.bevel_depth, curve.bevel_resolution = S["extrude"], S["bevel"], 4
    obj = bpy.data.objects.new("tmp", curve)
    scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.curves.remove(curve)
    return mesh

def span(body, axis=0):
    mesh = curve_mesh(body, solid=False)
    vals = [v.co[axis] for v in mesh.vertices]
    bpy.data.meshes.remove(mesh)
    return (min(vals), max(vals)) if vals else (0.0, 0.0)

_h = span("H", 1)
CAP = _h[1] - _h[0]                      # cap height of the font at size 1
_hh = span("HH")
HH = _hh[1] - _hh[0]
XS = S["x_scale"]
_glyphs = {}

def glyph(ch):
    """-> (mesh or None, advance, x of the glyph centre from the pen). Font units."""
    if ch not in _glyphs:
        a = span("H" + ch + "H")
        adv = (a[1] - a[0]) - HH
        if not ch.strip():
            _glyphs[ch] = (None, adv, 0.0, 0.0)
        else:
            mesh = curve_mesh(ch)
            if not mesh.vertices:
                raise ValueError(f"The font has no glyph for {ch!r}")
            mesh.name = "Glyph " + ch
            mesh.materials.append(GOLD)
            mesh.materials.append(SILVER)
            xs = [v.co.x for v in mesh.vertices]
            cx = (min(xs) + max(xs)) / 2
            for p in mesh.polygons:
                p.material_index = int(p.normal.z > .9999)
                p.use_smooth = p.material_index == 0      # flat face = true mirror
            for v in mesh.vertices:
                v.co.x -= cx
                v.co.y -= CAP / 2
            mesh.update()
            _glyphs[ch] = (mesh, adv, cx, max(xs) - min(xs))
    return _glyphs[ch]

# ------------------------------------------------------------------ layout
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
lines = []
for i, spec in enumerate(shot["lines"]):
    text = str(spec["text"]).upper()
    counter = spec.get("counter")
    if counter and not NUM.search(text):
        raise ValueError(f"Line {i + 1}: a counter needs a number in the text")
    tab = bool(counter) and spec.get("tabular", True)
    digit_w = max(glyph(d)[3] for d in "0123456789") + S["digit_gap"] if tab else 0
    slots, pen = [], 0.0                 # (char, centre x, advance)
    for ch in text:
        mesh, adv, cx, w = glyph(ch)
        if tab and ch.isdigit():
            slots.append((ch, pen + digit_w / 2, digit_w))
            pen += digit_w
        else:
            slots.append((ch, pen + cx, adv))
            pen += adv
    inked = [(c, x) for c, x, a in slots if c.strip()]
    left = inked[0][1] - glyph(inked[0][0])[3] / 2
    right = inked[-1][1] + glyph(inked[-1][0])[3] / 2
    height = float(spec.get("height", 1.5 if counter or NUM.fullmatch(text) else 0.72))
    scale = min(height / CAP, S["max_width"] / ((right - left) * XS))
    lines.append({"spec": spec, "text": text, "slots": slots, "scale": scale, "counter": counter,
                  "mid": (left + right) / 2, "cap": CAP * scale, "width": (right - left) * XS * scale})

total = sum(l["cap"] for l in lines) + S["line_gap"] * (len(lines) - 1)
y = total / 2
for l in lines:
    l["y"] = y - l["cap"] / 2
    y -= l["cap"] + S["line_gap"]
hero = next((l for l in lines if l["spec"].get("hero")), max(lines, key=lambda l: l["cap"]))

# ------------------------------------------------------------------ animation
cues = []

def cue(kind, frame, label):
    cues.append({"type": kind, "frame": frame, "label": label})

def put(line, ch, x, name):
    mesh = glyph(ch)[0]
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.parent = line["rig"]
    s = line["scale"]
    obj.location = ((x - line["mid"]) * XS * s, 0, 0)
    obj.scale = (s * XS, s, s)
    return obj

def ease_keys(obj, prop, f0, f1, a, b, overshoot=None):
    key(obj, prop, f0, a)
    if overshoot is not None:
        key(obj, prop, f1, overshoot)
        key(obj, prop, f1 + max(2, D(.14)), b)
    else:
        key(obj, prop, f1, b)

LINE_IN = {"turn": 1.9, "slam": 0.32, "push": 1.2, "cut": 0}
CHAR_IN = {"flip": 0.3, "rise": 0.5, "drop": 0.42}

for n, line in enumerate(lines):
    spec, s, cap = line["spec"], line["scale"], line["cap"]
    label = line["text"]
    rig = bpy.data.objects.new(f"Line {n + 1} • {label}", None)
    scene.collection.objects.link(rig)
    rig.location = (0, line["y"], 0)
    line["rig"] = rig
    anim = dict(spec.get("in", {}))
    kind = anim.get("type", "cut" if line["counter"] else "turn")
    at = F(float(anim.get("at", 0)))
    chars = []                           # static glyph objects of this line
    counter = line["counter"]
    num = NUM.search(line["text"]) if counter else None
    for i, (ch, x, adv) in enumerate(line["slots"]):
        if not ch.strip() or (num and num.start() <= i < num.end()):
            continue
        chars.append(put(line, ch, x, f"{label} • {i + 1} {ch}"))

    landed = at
    if kind in LINE_IN:
        dur = D(float(anim.get("duration", LINE_IN[kind])))
        landed = at + dur
        if kind == "turn":               # gold edge first, lingering before the face arrives
            key(rig, "rotation_euler", at, (0, math.radians(-80), 0))
            key(rig, "rotation_euler", at + int(dur * .6), (0, math.radians(-52), 0))
            key(rig, "rotation_euler", landed, (0, math.radians(-4), 0))
            key(rig, "rotation_euler", landed + D(1.1), (0, 0, 0))
        elif kind == "slam":             # from in front of the lens down onto its mark
            ease_keys(rig, "scale", at, landed, (3.4, 3.4, 3.4), (1, 1, 1), overshoot=(.955, .955, .955))
            key(rig, "location", at, (0, line["y"] * .3, 7))
            key(rig, "location", landed, (0, line["y"], 0))
        elif kind == "push":             # arrives from deep in the set
            key(rig, "location", at, (0, line["y"], -42))
            key(rig, "location", landed, (0, line["y"], 0))
        for o in chars:
            show(o, at)
    elif kind in CHAR_IN:
        dur = D(float(anim.get("duration", CHAR_IN[kind])))
        stagger = float(anim.get("stagger", 0.06)) * FPS / SPEED
        for j, o in enumerate(chars):
            f0 = at + int(round(j * stagger))
            f1 = f0 + dur
            x0 = o.location.x
            if kind == "flip":
                key(o, "rotation_euler", f0, (math.radians(-88), -.09, 0))
                key(o, "rotation_euler", f1, (0, 0, 0))
            elif kind == "rise":
                key(o, "location", f0, (x0, -cap * 1.1, -.6))
                key(o, "location", f1, (x0, 0, 0))
                key(o, "rotation_euler", f0, (math.radians(55), 0, 0))
                key(o, "rotation_euler", f1, (0, 0, 0))
            elif kind == "drop":
                ease_keys(o, "location", f0, f1, (x0, cap * 2.2, 1.5), (x0, 0, 0), overshoot=(x0, -cap * .06, 0))
            show(o, f0)
            cue("tick", f1, f"{label}: {o.name.split()[-1]} lands")
            landed = max(landed, f1)
    else:
        raise ValueError(f"Line {n + 1}: unknown in.type {kind!r}")
    line["at"] = at
    cue("in", at, f"{label}: {kind} starts")

    if counter:
        mode = counter.get("mode", "flip")
        c0 = F(float(counter["at"])) if "at" in counter else landed
        digits = [(i, line["slots"][i]) for i in range(num.start(), num.end())]
        if mode == "flip":               # each position flips through two decoys onto its digit
            phase, flip = D(.32), D(.28)
            spread = D(float(counter.get("duration", 1.7))) - 2 * phase - flip
            for j, (i, (ch, x, adv)) in enumerate(digits):
                arrive = c0 + int(round(max(0, spread) * j / max(1, len(digits) - 1)))
                steps = [str((int(ch) + k) % 10) for k in (4, 7, 0)] if ch.isdigit() else [ch]
                for k, sym in enumerate(steps):
                    o = put(line, sym, x, f"{label} • position {i + 1} • {sym}")
                    f0 = arrive + phase * k
                    show(o, f0, f0 + phase if k < len(steps) - 1 else None)
                    key(o, "rotation_euler", f0, (math.radians(-72), -.09, 0))
                    key(o, "rotation_euler", f0 + flip, (0, -.035 if k < len(steps) - 1 else 0, 0))
                    cue("tick", f0, f"{label}: position {i + 1} flips")
                    landed = max(landed, f0 + flip)
        elif mode == "count":            # counts up from zero, easing into the final figure
            c1 = c0 + D(float(counter.get("duration", 1.8)))
            final = num.group()
            decimals = len(final.split(".")[1]) if "." in final else 0
            target = float(final.replace(",", ""))
            grouped = "," in final
            made, last = {}, None
            for f in range(c0, c1 + 1):
                p = (f - c0) / max(1, c1 - c0)
                v = target * (1 - (1 - p) ** 3)
                txt = f"{v:,.{decimals}f}" if grouped else f"{v:.{decimals}f}"
                if f == c1:
                    txt = final
                txt = txt.rjust(len(final))[-len(final):]
                if txt == last:
                    continue
                for (i, (ch, x, adv)), sym in zip(digits, txt):
                    prev = last[i - num.start()] if last else " "
                    if sym == prev:
                        continue
                    if prev.strip():
                        for prop in ("hide_render", "hide_viewport"):   # hide the outgoing figure
                            key(made[(i, prev)][-1], prop, f, True)
                    if sym.strip():
                        o = put(line, sym, x, f"{label} • position {i + 1} • {sym} @{f}")
                        for prop in ("hide_render", "hide_viewport"):
                            key(o, prop, 1, True)
                            key(o, prop, f, False)
                        made.setdefault((i, sym), []).append(o)
                if f - c0 >= 2 and (f - c0) % 2 == 0 and f < c1:
                    cue("tick", f, f"{label}: counting")
                last = txt
            landed = c1
            ease_keys(rig, "scale", c1 - 1, c1, (1, 1, 1), (1.07, 1.07, 1.07))
            key(rig, "scale", c1 + D(.24), (1, 1, 1))
        else:
            raise ValueError(f"Line {n + 1}: unknown counter.mode {mode!r}")
        cue("in", c0, f"{label}: counter starts")
    line["landed"] = landed
    cue("impact", landed, f"{label} lands")

    out = spec.get("out")
    if out:
        okind, o0 = out.get("type", "cut"), F(float(out["at"]))
        o1 = o0 + D(float(out.get("duration", .5)))
        members = [c for c in rig.children]
        if okind == "turn":
            key(rig, "rotation_euler", o0, (0, 0, 0))
            key(rig, "rotation_euler", o1, (0, math.radians(86), 0))
        elif okind == "push":            # flies past the lens
            key(rig, "location", o0, (0, line["y"], 0))
            key(rig, "location", o1, (0, line["y"] * .2, 19))
        elif okind == "drop":
            key(rig, "location", o0, (0, line["y"], 0))
            key(rig, "location", o1, (0, line["y"] - 9, 0))
        elif okind != "cut":
            raise ValueError(f"Line {n + 1}: unknown out.type {okind!r}")
        hide_at = o0 if okind == "cut" else o1
        for c in members:
            for prop in ("hide_render", "hide_viewport"):
                c.keyframe_insert(data_path=prop, frame=hide_at - 1)
                key(c, prop, hide_at, True)
        line["gone"] = hide_at
        cue("out", o0, f"{label}: {okind} out")

impacts = sorted({c["frame"] for c in cues if c["type"] == "impact"})
last_event = max([c["frame"] for c in cues])
END = F(float(shot["duration"])) - 1 if "duration" in shot else last_event + D(2.4 * SPEED)
scene.frame_start, scene.frame_end = 1, END
cue("hold", min(END, impacts[-1] + D(.4)), "everything settled")

# ------------------------------------------------------------------ lights
from mathutils import Vector

def aim(obj, target=(0, 0, 0)):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

def light(name, xyz, width, height, watts, tint):
    data = bpy.data.lights.new(name, "AREA")
    data.shape = "RECTANGLE"
    data.size, data.size_y = width, height
    data.energy, data.color = watts * .24, tint
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = xyz
    aim(obj)
    return obj

light("Silk • white overhead", (0, 4, 5), 14, 3.5, 1350, (1, .94, .84))
light("Strip • lower silver", (-1, -4.6 - total / 2 + 1.3, 6), 12, 1.6, 1050, (.88, .92, 1))
light("Tall warm edge", (9.5, 1, 2), 2.5, 8, 980, (1, .65, .31))
if FX["sweep"]:
    sw = FX["sweep"] if isinstance(FX["sweep"], dict) else {}
    s0 = F(float(sw.get("at", 0)))
    s1 = s0 + D(float(sw.get("duration", (impacts[-1] - 1) / FPS * SPEED + .3)))
    sweep = light("Travelling softbox", (-7, 0, 7), 2.5, 8, 700, (1, .82, .58))
    for t, x in ((s0, -13), (s1, 13)):
        key(sweep, "location", t, (x, 0, 7))
        aim(sweep)
        sweep.keyframe_insert(data_path="rotation_euler", frame=t)
    cue("sweep", s0, "light sweep starts")

# Emissive studio cards: reflected in the metal, hidden from camera.
def card(name, xyz, w, h, rot=(0, 0, 0)):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.location, obj.rotation_euler = xyz, rot
    obj.visible_camera = False
    obj.visible_shadow = False
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    mesh.materials.append(mat)
    return obj, mat.node_tree

def emit(nt, color, strength, ramp=None):
    em, out = nt.nodes.new("ShaderNodeEmission"), nt.nodes.new("ShaderNodeOutputMaterial")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    if ramp:
        co, sep, rp = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeSeparateXYZ"), nt.nodes.new("ShaderNodeValToRGB")
        rp.color_ramp.interpolation = "EASE"
        (p0, c0), (p1, c1) = ramp
        rp.color_ramp.elements[0].position, rp.color_ramp.elements[0].color = p0, (*c0, 1)
        rp.color_ramp.elements[1].position, rp.color_ramp.elements[1].color = p1, (*c1, 1)
        nt.links.new(co.outputs["Generated"], sep.inputs[0])
        nt.links.new(sep.outputs["Y"], rp.inputs["Fac"])
        nt.links.new(rp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs[0])
    return em

# ------------------------------------------------------------------ camera
cam_spec = {"move": "push_in", "lens": 55}
cam_spec.update(shot.get("camera", {}))
shake_rig = bpy.data.objects.new("Shake rig", None)
scene.collection.objects.link(shake_rig)
cam_data = bpy.data.cameras.new("Title lens")
cam = bpy.data.objects.new("Centred camera", cam_data)
scene.collection.objects.link(cam)
cam.parent = shake_rig
scene.camera = cam
cam_data.lens = cam_spec["lens"]
fit = max(1.0, total / 5.2)              # pull back for tall stacks
move, first = cam_spec["move"], impacts[0]
if move == "static":
    keys = [(1, 0, 17.5)]
elif move == "push_in":
    keys = [(1, 0, 18.4), (END, 0, 16.6)]
elif move == "pull_back":
    keys = [(1, 0, 16.4), (END, 0, 18.2)]
elif move == "reveal":                   # starts tight on the first line's edge, opens to the full frame
    y0 = min(lines, key=lambda l: (l["at"], l["counter"] is not None))["y"]
    keys = [(1, y0, 9), (max(2, first - D(.1)), y0 * .6, 18.2), (first + D(1.6), 0, 17.5), (END, 0, 16.8)]
else:
    raise ValueError(f"unknown camera.move {move!r}")
for t, cy, cz in keys:
    key(cam, "location", t, (0, cy, cz * fit))
HOLD_Z = keys[-1][2] * fit
if FX["shake"]:
    key(shake_rig, "location", 1, (0, 0, 0))
    for f in impacts:
        key(shake_rig, "location", f - 1, (0, 0, 0))
        for k in range(9):
            a = float(FX["shake"]) * .16 * math.exp(-k * .5)
            key(shake_rig, "location", f + k, (rng.uniform(-a, a), rng.uniform(-a, a), 0))
        key(shake_rig, "location", f + 9, (0, 0, 0))
if FX["dof"]:                            # soft at the reveal, crisp by the first landing
    target = bpy.data.objects.new("Focus", None)
    scene.collection.objects.link(target)
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = target
    for t, stop in ((1, .12), (max(2, first - D(.5)), .3), (first, 16)):
        cam_data.dof.aperture_fstop = stop
        cam_data.dof.keyframe_insert(data_path="aperture_fstop", frame=t)

# A flat face at z=0 mirrors the plane behind the camera, magnified by (card z + camera z) / camera z.
SILK_Z = HOLD_Z + 7
mag = (SILK_Z - .5 + HOLD_Z) / HOLD_Z
_, nt = card("Silk • graded, behind camera", (0, 0, SILK_Z), 48 * fit, 26 * fit)
emit(nt, (1, 1, 1), S["silk_strength"], ramp=((.40, (.12, .115, .105)), (.62, (.46, .45, .43))))
# One long strip per hero-sized line, so each big row carries a single clean highlight.
for l in lines:
    if l["cap"] < hero["cap"] * .85:
        continue
    band_y = (l["y"] + S["band_height"] * l["cap"]) * mag
    _, nt = card("Strip • long highlight • " + l["text"], (0, band_y, SILK_Z - .5), 30 * fit, S["band_width"] * l["cap"] / 1.5)
    band = emit(nt, (1, .97, .92), S["band_strength"])
    if FX["glint"]:                      # the strip flares as its line lands
        strength = band.inputs["Strength"]
        for f, v in ((1, 1), (l["landed"] - 2, 1), (l["landed"] + 1, 5), (l["landed"] + D(.5), 1)):
            strength.default_value = S["band_strength"] * v
            strength.keyframe_insert("default_value", frame=max(1, f))
for side in (-1, 1):
    _, nt = card("Gold bounce • " + ("left" if side < 0 else "right"), (side * 9.5, 0, 5), 7, 9, (0, math.radians(side * -68), 0))
    emit(nt, (1, .60, .24), S["gold_bounce"])

# Defocused champagne practicals around the outside of the title.
if S["practicals"] and not args.alpha:
    glow = bpy.data.materials.new("Soft amber practical")
    glow.use_nodes = True
    nt = glow.node_tree
    nt.nodes.clear()
    tex, dist = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeVectorMath")
    dist.operation = "LENGTH"
    nt.links.new(tex.outputs["Object"], dist.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (.65, .33, .09, 1)
    ramp.color_ramp.elements[1].position = .5
    ramp.color_ramp.elements[1].color = (*S["background"], 1)
    ramp.color_ramp.interpolation = "EASE"
    nt.links.new(dist.outputs["Value"], ramp.inputs[0])
    em, out = nt.nodes.new("ShaderNodeEmission"), nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(ramp.outputs[0], em.inputs[0])
    nt.links.new(em.outputs[0], out.inputs[0])
    unit = bpy.data.meshes.new("Practical")
    unit.from_pydata([(-.5, -.5, 0), (.5, -.5, 0), (.5, .5, 0), (-.5, .5, 0)], [], [(0, 1, 2, 3)])
    unit.materials.append(glow)
    for _ in range(int(S["practicals"])):
        b = bpy.data.objects.new("Distant practical", unit)
        scene.collection.objects.link(b)
        b.location = (rng.choice([-1, 1]) * rng.uniform(5.0, 8.6) * fit, rng.uniform(-4, 4) * fit, -3 - rng.random() * 2)
        size = rng.uniform(.03, .27)
        b.scale = (size, size, 1)

# ------------------------------------------------------------------ output
cues.sort(key=lambda c: (c["frame"], c["type"]))
for c in cues:
    c["seconds"] = round((c["frame"] - 1) / FPS, 3)
    scene.timeline_markers.new(c["label"][:60], frame=c["frame"])
(OUT / "cues.json").write_text(json.dumps({
    "name": NAME, "fps": FPS, "frames": END, "seconds": round(END / FPS, 3),
    "width": W, "height": H, "alpha": args.alpha, "cues": cues}, indent=2))
scene.frame_set(min(END, impacts[-1] + D(.6)))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{NAME}.blend"))

if args.stills:
    for f in args.stills.split(","):
        f = END if f == "last" else (min(END, impacts[-1] + D(.6)) if f == "hold" else int(f))
        scene.frame_set(f)
        scene.render.filepath = str(OUT / f"{NAME}-still-{f:04d}.png")
        bpy.ops.render.render(write_still=True)
if args.anim:
    (OUT / "frames").mkdir(exist_ok=True)
    scene.render.use_overwrite = False      # re-running resumes a part-finished render
    scene.render.filepath = str(OUT / "frames" / "f-")
    bpy.ops.render.render(animation=True)
print(f"ENGINE OK {NAME} frames={END} out={OUT}")
