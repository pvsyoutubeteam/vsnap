"""Run in a fresh background Blender process (see CLAUDE.md)."""
from pathlib import Path
import json
import math
import random

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
cfg = json.loads((ROOT / "shot.json").read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 48
scene.cycles.use_denoising = False
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 50
scene.render.fps = 25
scene.frame_end = 150
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = "//frames/sales-"

def material(name, color, roughness, metal):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Metallic"].default_value = metal
    bs.inputs["Roughness"].default_value = roughness
    return mat

silver = material("Polished silver • face", (.86,.88,.92), cfg["face_roughness"], 1)
gold = material("Champagne • bevel and sides", (.86,.51,.20), cfg["gold_roughness"], 1)
world = bpy.data.worlds.new("Black studio")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (.012,.012,.017,1)
# A broad studio silk and two narrow white strips reflected in the polished faces.
# Per-glyph coordinates keep the reflected horizon continuous across a row.
nt = silver.node_tree
coords = nt.nodes.new("ShaderNodeTexCoord")
split = nt.nodes.new("ShaderNodeSeparateXYZ")
nt.links.new(coords.outputs["Generated"], split.inputs[0])
r = nt.nodes.new("ShaderNodeValToRGB")
r.color_ramp.interpolation = "EASE"
bands = [(0,(.28,.20,.14)),(.12,(.77,.74,.70)),(.25,(.11,.10,.095)),
         (.39,(.045,.048,.054)),(.48,(.52,.39,.25)),(.54,(.97,.91,.77)),
         (.59,(.32,.31,.30)),(.79,(.63,.65,.67)),(.96,(.88,.88,.85)),(1,(.45,.40,.35))]
for i,(v,col) in enumerate(bands):
    el = r.color_ramp.elements[0] if i == 0 else (r.color_ramp.elements[-1] if v == 1 else r.color_ramp.elements.new(v))
    el.color = (*col,1)
nt.links.new(split.outputs["Y"],r.inputs["Fac"])
bs = nt.nodes.get("Principled BSDF")
nt.links.new(r.outputs["Color"],bs.inputs["Emission Color"])
bs.inputs["Emission Strength"].default_value = .83

font = bpy.data.fonts.load(str(ROOT / cfg["font"]))
font.pack()

def key(obj, prop, t, value):
    setattr(obj, prop, value)
    obj.keyframe_insert(data_path=prop, frame=t)

def type_mesh(body):
    curve = bpy.data.curves.new(body, "FONT")
    curve.body = body
    curve.font = font
    curve.extrude = .08
    curve.bevel_depth = .012
    curve.bevel_resolution = 4
    curve.resolution_u = 12
    curve.space_character = .96
    obj = bpy.data.objects.new(body, curve)
    scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.curves.remove(curve)
    mesh.materials.append(gold)
    mesh.materials.append(silver)
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    dx, dy = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    for p in mesh.polygons:
        p.material_index = int(p.normal.z > .9999)
    for v in mesh.vertices:
        v.co.x -= dx
        v.co.y -= dy
    mesh.update()
    return mesh, max(xs)-min(xs)

def place(name, mesh, xyz, scale):
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.location = xyz
    obj.scale = scale
    return obj

mesh, width = type_mesh(cfg["label"].upper())
k = min(4.6/width, 1.55)
label = place("Category • " + cfg["label"], mesh, (0,-.92,0), (k*1.15,k,k))
key(label, "rotation_euler", 1, (0,math.radians(-82),0))
key(label, "rotation_euler", 48, (0,-.07,0))
key(label, "rotation_euler", 78, (0,0,0))

value = cfg["display_value"]
if not value.strip() or any(ch not in "0123456789.,£%+-" for ch in value):
    raise ValueError("display_value requires digits or supported punctuation")
glyphs = {ch:type_mesh(ch) for ch in set("0123456789"+value)}
slots = [.55 if ch.isdigit() else glyphs[ch][1]+.12 for ch in value]
size = min(3.1, 9.1/sum(slots))
left = -sum(slots)*size/2
for i, (ch, slot) in enumerate(zip(value, slots)):
    x = left+slot*size/2
    left += slot*size
    phases = [str((int(ch)+n)%10) for n in (4,7,0)] if ch.isdigit() else [ch]
    arrival = 48+round(19*i/max(1,len(value)-1))
    for j, symbol in enumerate(phases):
        mesh, _ = glyphs[symbol]
        y = .48 if symbol in ",." else .78
        obj = place(f"Position {i+1} • {symbol}",mesh,(x,y,0),(size*1.10,size,size))
        start = arrival+8*j
        for prop in ("hide_render","hide_viewport"):
            key(obj, prop, 1, True)
            key(obj, prop, start, False)
            if j < len(phases)-1:
                key(obj, prop, start+8, True)
        key(obj,"rotation_euler",start,(math.radians(-72),-.09,0))
        key(obj,"rotation_euler",start+7,(0,-.035,0))

def aim(obj, target):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()

def light(name, xyz, width, height, watts, tint):
    data = bpy.data.lights.new(name,"AREA")
    data.shape = "RECTANGLE"
    data.size, data.size_y = width,height
    data.energy, data.color = watts*.24,tint
    obj = bpy.data.objects.new(name,data)
    scene.collection.objects.link(obj)
    obj.location = xyz
    aim(obj,(0,0,0))
    return obj

light("Silk • white overhead",(0,4,5),14,3.5,1350,(1,.94,.84))
light("Strip • lower silver",(-1,-3,6),12,1.6,1050,(.88,.92,1))
light("Tall warm edge",(6,1,2),2.5,8,980,(1,.65,.31))
sweep = light("Travelling softbox",(-5,0,7),2.5,8,700,(1,.82,.58))
for t,x in [(1,-7),(62,-2),(105,5)]:
    key(sweep,"location",t,(x,0,7))
    aim(sweep,(0,0,0))
    sweep.keyframe_insert(data_path="rotation_euler",frame=t)

cam_data = bpy.data.cameras.new("Title lens")
cam = bpy.data.objects.new("Centred camera",cam_data)
scene.collection.objects.link(cam)
cam.rotation_euler = (0,0,0)
scene.camera = cam
cam_data.lens = 55
for t,y,z in [(1,-.90,9),(47,-.55,18.2),(89,0,17.5),(150,0,16.8)]:
    key(cam,"location",t,(0,y,z))

# Defocused champagne practicals, scattered around the outside of the title.
rng = random.Random(42)
glow = bpy.data.materials.new("Soft amber practical")
glow.use_nodes = True
nt = glow.node_tree
nt.nodes.clear()
def node(typ):
    return nt.nodes.new(typ)
tex, dist = node("ShaderNodeTexCoord"), node("ShaderNodeVectorMath")
dist.operation = "DISTANCE"
dist.inputs[1].default_value = (.5,.5,0)
nt.links.new(tex.outputs["UV"],dist.inputs[0])
ramp = node("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (.65,.33,.09,1)
ramp.color_ramp.elements[1].position = .52
ramp.color_ramp.elements[1].color = (.012,.012,.017,1)
ramp.color_ramp.interpolation = "EASE"
nt.links.new(dist.outputs["Value"],ramp.inputs[0])
em, out = node("ShaderNodeEmission"), node("ShaderNodeOutputMaterial")
nt.links.new(ramp.outputs[0],em.inputs[0])
nt.links.new(em.outputs[0],out.inputs[0])
for n in range(36):
    x = rng.choice([-1,1])*rng.uniform(5.0,8.6)
    bpy.ops.mesh.primitive_plane_add(size=rng.uniform(.03,.27),location=(x,rng.uniform(-4,4),-3-rng.random()*2))
    b = bpy.context.object
    b.name = "Distant practical"
    b.data.materials.append(glow)

for name,t in [("Gold edge",1),("Riser",40),("Counter in",48),("Impact",90),("Hold",100)]:
    scene.timeline_markers.new(name,frame=t)
scene.frame_set(110)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"AwardsType.blend"))
