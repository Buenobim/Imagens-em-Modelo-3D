# -*- coding: utf-8 -*-
"""
Leitura, escrita e VALIDACAO de STL binario (so numpy; roda no Blender e no Python do projeto).
Validador herdado do repositorio Impress-o3D_Carros: reabre o arquivo gravado e confere
solido fechado, orientado, sem triangulos degenerados e dentro da mesa.
"""
import os
import numpy as np

BED = 180.0

_DT = np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")])

def write_stl(path, tris, header=b"Imagens em Modelo 3D (mm)"):
    tris = np.asarray(tris, dtype=np.float64)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    data = np.zeros(len(tris), dtype=_DT)
    data["n"] = n
    data["v"] = tris.reshape(-1, 9)
    with open(path, "wb") as f:
        f.write(header.ljust(80, b" ")[:80])
        f.write(np.uint32(len(tris)).tobytes())
        f.write(data.tobytes())

def read_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        n = int(np.frombuffer(f.read(4), dtype="<u4")[0])
        data = np.frombuffer(f.read(n * 50), dtype=_DT)
    return data["v"].reshape(-1, 3, 3).astype(np.float64)

def _shells(F, nverts):
    parent = np.arange(nverts)
    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root
    for a, b in np.concatenate([F[:, [0, 1]], F[:, [1, 2]]]):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return len({find(v) for v in np.unique(F)})

def validate_stl(path, bed=BED, check_bed=True):
    tris = read_stl(path)
    key = np.round(tris.reshape(-1, 3) / 1e-4).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    F = inv.reshape(-1, 3)
    area = 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
    degenerate = int(np.sum(area < 1e-8) + np.sum((F[:, 0] == F[:, 1]) | (F[:, 1] == F[:, 2]) | (F[:, 0] == F[:, 2])))
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    _, cnt = np.unique(np.sort(E, axis=1), axis=0, return_counts=True)
    nonmanifold = int(np.sum(cnt != 2))
    _, dcnt = np.unique(E, axis=0, return_counts=True)
    misoriented = int(np.sum(dcnt > 1))
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    # volume com sinal (positivo = normais para fora)
    vol = float(np.sum(np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2]))) / 6.0)
    rep = dict(arquivo=os.path.basename(path), triangulos=len(tris), cascas=_shells(F, inv.max() + 1),
               arestas_nao_manifold=nonmanifold, arestas_mal_orientadas=misoriented,
               triangulos_degenerados=degenerate, caixa_mm=[round(float(v), 2) for v in (hi - lo)],
               volume_cm3=round(vol / 1000.0, 2))
    ok = nonmanifold == 0 and misoriented == 0 and degenerate == 0 and vol > 0 and lo[2] > -1e-3
    if check_bed:
        ok = ok and (hi - lo)[0] <= bed and (hi - lo)[1] <= bed and (hi - lo)[2] <= bed
    rep["ok"] = bool(ok)
    return rep
