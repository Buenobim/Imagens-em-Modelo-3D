# -*- coding: utf-8 -*-
"""Prepara a malha para impressao: Blender (pos_processar.py) + fatiamento verificado (Bambu Studio)."""
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
sys.path.insert(0, os.path.join(RAIZ, "impressao"))

# slots do AMS (mesmos do repositorio dos carros)
CORES = {
    "1 · Vermelho": (1, (0.62, 0.03, 0.03)),
    "2 · Preto": (2, (0.06, 0.06, 0.06)),
    "3 · Prata": (3, (0.72, 0.74, 0.78)),
    "4 · Branco": (4, (0.93, 0.93, 0.90)),
}
CAMADAS = {"Fina (0,12 mm)": "0.12", "Ótima (0,16 mm)": "0.16", "Padrão (0,20 mm)": "0.20"}
PEDESTAIS = {"Sem pedestal": "nenhum", "Redondo": "redondo", "Retangular": "retangular"}

def preparar(pasta, glb, tamanho_mm, medida, corte_base_mm, pedestal, cor, suporte, camada):
    """roda o Blender e o fatiador; devolve (info_impressao, info_fatiamento)"""
    slot, rgb = CORES[cor]
    # orientacao de saida da IA: o 2.1 entrega olhando para -X (gira 90 graus); o 2.0, para -Y
    motor = "v21"
    try:
        motor = json.load(open(os.path.join(pasta, "geracao.json"), encoding="utf-8")).get("motor") or "v21"
    except Exception:
        pass
    params = dict(entrada=glb, saida_dir=pasta, nome="modelo", tamanho_mm=float(tamanho_mm),
                  medida="altura" if medida.startswith("Altura") else "maior",
                  corte_base_mm=float(corte_base_mm), pedestal=PEDESTAIS[pedestal], cor_rgb=list(rgb),
                  girar_graus=90 if motor == "v21" else 0)
    pj = os.path.join(pasta, "parametros_impressao.json")
    json.dump(params, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                        "-P", os.path.join(RAIZ, "blender", "pos_processar.py"), "--", pj],
                       capture_output=True, text=True, errors="ignore")
    log = "\n".join(l for l in r.stdout.splitlines() if l.startswith("[pos]"))
    if r.returncode != 0:
        raise RuntimeError("Falha ao preparar a malha no Blender:\n" + log + "\n" + r.stderr[-1500:])
    info = json.load(open(os.path.join(pasta, "impressao.json"), encoding="utf-8"))
    import fatiar_modelo
    fat = fatiar_modelo.fatiar(info["stl"], suporte=bool(suporte), slot=slot, camada=CAMADAS[camada])
    return info, fat
