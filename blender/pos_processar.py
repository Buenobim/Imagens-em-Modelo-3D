# -*- coding: utf-8 -*-
"""
Pos-processamento no Blender: malha gerada pela IA (GLB) -> peca IMPRIMIVEL (STL validado).

  blender -b --factory-startup --python-exit-code 1 -P blender/pos_processar.py -- parametros.json

Passos:
 1. importa o GLB, junta as partes e escala para o tamanho pedido (mm)
 2. refaz a malha por VOXEL (fecha furos, remove faces internas -> solido fechado garantido)
 3. reduz o numero de triangulos (mantem o detalhe visivel com bico 0,4)
 4. corta uma fatia de baixo para criar uma BASE PLANA (gruda na mesa)
 5. pedestal opcional (redondo ou retangular) para pecas com apoio pequeno
 6. exporta o STL, REABRE e valida (fechado, orientado, sem degenerados, cabe na mesa)
 7. renders de previa
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Matrix, Vector

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))
from stl_util import write_stl, validate_stl
import numpy as np

P = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))
SAIDA = os.path.abspath(P["saida_dir"])          # o Blender resolve caminho relativo de outro jeito
os.makedirs(SAIDA, exist_ok=True)

def log(*a):
    print("[pos]", *a, flush=True)

def limpar_cena():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)

def aplicar_modificador(ob, mod):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.remove(mod)
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)

def booleano(alvo, cortador, op):
    mod = alvo.modifiers.new("B", "BOOLEAN")
    mod.operation = op
    mod.object = cortador
    mod.solver = "MANIFOLD"
    aplicar_modificador(alvo, mod)
    bpy.data.objects.remove(cortador, do_unlink=True)

def caixa(x0, x1, y0, y1, z0, z1):
    me = bpy.data.meshes.new("caixa")
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me.from_pydata(v, [], f)
    ob = bpy.data.objects.new("caixa", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob

def pedestal(forma, cx, cy, rx, ry, h):
    me = bpy.data.meshes.new("pedestal")
    bm = bmesh.new()
    n = 96
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        if forma == "redondo":
            pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
        else:   # retangular com cantos arredondados (superelipse)
            c, s = math.cos(a), math.sin(a)
            pts.append((cx + rx * math.copysign(abs(c) ** 0.25, c), cy + ry * math.copysign(abs(s) ** 0.25, s)))
    bot = [bm.verts.new((x, y, 0)) for x, y in pts]
    top = [bm.verts.new((x, y, h)) for x, y in pts]
    bm.faces.new(bot[::-1])
    bm.faces.new(top)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    # chanfro de 45 graus na borda de cima (acabamento)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("pedestal", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob

def tri_world(ob):
    me = ob.data
    me.calc_loop_triangles()
    co = np.array([v.co[:] for v in me.vertices])
    idx = np.array([lt.vertices[:] for lt in me.loop_triangles])
    return co[idx]

# ---------------------------------------------------------------------------
limpar_cena()
bpy.ops.import_scene.gltf(filepath=os.path.abspath(P["entrada"]))
malhas = [o for o in bpy.context.scene.objects if o.type == "MESH"]
for o in bpy.context.scene.objects:
    o.select_set(o.type == "MESH")
bpy.context.view_layer.objects.active = malhas[0]
if len(malhas) > 1:
    bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for o in list(bpy.context.scene.objects):
    if o != ob:
        bpy.data.objects.remove(o, do_unlink=True)
# o Hunyuan3D entrega o modelo olhando para -X (apos importar o glTF); gira para olhar para -Y (frente)
ob.data.transform(Matrix.Rotation(math.radians(90), 4, "Z"))
log("importado:", len(ob.data.vertices), "vertices")

# 1. escala
d = ob.dimensions
ref = d.z if P.get("medida", "altura") == "altura" else max(d)
s = float(P["tamanho_mm"]) / ref
ob.data.transform(Matrix.Scale(s, 4))
co = np.array([v.co[:] for v in ob.data.vertices])
lo, hi = co.min(0), co.max(0)
ob.data.transform(Matrix.Translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])))
dims = hi - lo
log("escala:", round(s, 4), "-> dimensoes", np.round(dims, 1))

# 2. remalha por voxel
voxel = float(P.get("voxel_mm") or max(0.12, float(max(dims)) / 500.0))
mod = ob.modifiers.new("R", "REMESH")
mod.mode = "VOXEL"
mod.voxel_size = voxel
mod.adaptivity = 0.0
aplicar_modificador(ob, mod)
log("voxel", round(voxel, 3), "mm ->", len(ob.data.polygons), "faces")

# 3. reduz triangulos
max_faces = int(P.get("max_faces", 300000))
if len(ob.data.polygons) * 2 > max_faces:
    mod = ob.modifiers.new("D", "DECIMATE")
    mod.ratio = max_faces / (len(ob.data.polygons) * 2.0)
    aplicar_modificador(ob, mod)
    log("reduzido ->", len(ob.data.polygons), "faces")

# 4. base plana
corte = float(P.get("corte_base_mm", 0.0))
if corte > 0:
    booleano(ob, caixa(-500, 500, -500, 500, -500, corte), "DIFFERENCE")
    ob.data.transform(Matrix.Translation((0, 0, -corte)))
    log("base plana: cortado", corte, "mm")

# 5. pedestal
forma = P.get("pedestal", "nenhum")
if forma in ("redondo", "retangular"):
    h = float(P.get("pedestal_mm", 2.0))
    margem = float(P.get("pedestal_margem_mm", 3.0))
    co = np.array([v.co[:] for v in ob.data.vertices])
    baixo = co[co[:, 2] <= max(2.0, 0.08 * co[:, 2].max())]
    blo, bhi = baixo.min(0), baixo.max(0)
    cx, cy = (blo[0] + bhi[0]) / 2, (blo[1] + bhi[1]) / 2
    rx, ry = (bhi[0] - blo[0]) / 2 + margem, (bhi[1] - blo[1]) / 2 + margem
    if forma == "redondo":
        rx = ry = max(rx, ry)
    ob.data.transform(Matrix.Translation((0, 0, h - 0.4)))      # 0,4 mm de sobreposicao
    booleano(ob, pedestal(forma, cx, cy, rx, ry, h), "UNION")
    log("pedestal", forma, round(2 * rx, 1), "x", round(2 * ry, 1), "x", h, "mm")

# recentraliza, apoia em z=0
co = np.array([v.co[:] for v in ob.data.vertices])
lo, hi = co.min(0), co.max(0)
ob.data.transform(Matrix.Translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])))

# 6. exporta e valida (limpeza herdada do repositorio dos carros + rede de seguranca por voxel)
def limpar(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-4)     # precisao do STL (float32)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    for _ in range(6):                                           # lascas de area zero: gira a aresta longa
        bm.faces.ensure_lookup_table()
        arestas = set()
        for f in bm.faces:
            if f.calc_area() < 1e-9:
                e = max(f.edges, key=lambda e: e.calc_length())
                if len(e.link_faces) == 2:
                    arestas.add(e)
        if not arestas:
            break
        bmesh.ops.rotate_edges(bm, edges=list(arestas), use_ccw=False)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()

stl = os.path.join(SAIDA, P.get("nome", "modelo") + ".stl")
limpar(ob)
write_stl(stl, tri_world(ob))
rep = validate_stl(stl)
if not rep["ok"]:
    log("validacao falhou, refazendo por voxel:", rep)
    mod = ob.modifiers.new("R2", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = voxel
    mod.adaptivity = 0.0
    aplicar_modificador(ob, mod)
    if len(ob.data.polygons) * 2 > max_faces:
        mod = ob.modifiers.new("D2", "DECIMATE")
        mod.ratio = max_faces / (len(ob.data.polygons) * 2.0)
        aplicar_modificador(ob, mod)
    co = np.array([v.co[:] for v in ob.data.vertices])
    ob.data.transform(Matrix.Translation((0, 0, -co[:, 2].min())))
    limpar(ob)
    write_stl(stl, tri_world(ob))
    rep = validate_stl(stl)
log("validacao:", rep)

# 7. previas
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x = sc.render.resolution_y = 900
sh = sc.display.shading
sh.light = "STUDIO"
sh.color_type = "OBJECT"
sh.show_cavity = True
sh.cavity_type = "BOTH"
sh.show_shadows = True
if sc.world is None:
    sc.world = bpy.data.worlds.new("W")
sc.world.color = (0.94, 0.93, 0.91)
sc.view_settings.view_transform = "Standard"
rgb = P.get("cor_rgb", (0.62, 0.03, 0.03))
ob.color = (*rgb, 1)
co = np.array([v.co[:] for v in ob.data.vertices])
ctr = Vector(((co.min(0) + co.max(0)) / 2).tolist())
raio = float(np.linalg.norm(co.max(0) - co.min(0))) / 2
previas = []
for nome, direcao in (("frente", Vector((0.35, -1, 0.35))), ("tres_quartos", Vector((-0.8, -0.9, 0.55))),
                      ("costas", Vector((-0.3, 1, 0.35)))):
    cd = bpy.data.cameras.new("cam")
    cd.lens = 50
    cam = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(cam)
    dist = raio / math.tan(math.atan(18 / 50)) * 1.15
    cam.location = ctr + direcao.normalized() * dist
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    arq = os.path.join(SAIDA, f"previa_{nome}.png")
    sc.render.filepath = arq
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    previas.append(arq)

info = dict(parametros=P, voxel_mm=round(voxel, 3), stl=stl, previas=previas, validacao=rep,
            dimensoes_mm=rep["caixa_mm"], volume_cm3=rep["volume_cm3"])
json.dump(info, open(os.path.join(SAIDA, "impressao.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
if not rep["ok"]:
    raise SystemExit("VALIDACAO DO STL FALHOU: " + json.dumps(rep, ensure_ascii=False))
log("OK")
