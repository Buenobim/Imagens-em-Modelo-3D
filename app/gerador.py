# -*- coding: utf-8 -*-
"""
Geracao imagem -> malha 3D com o Hunyuan3D-2 (Tencent, modelo aberto) rodando NESTE computador.
O modelo e carregado uma vez e fica na placa de video.
Licenca dos pesos: Tencent Hunyuan 3D 2.0 Community License (vendor/Hunyuan3D-2/LICENSE).
"""
import os
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HY3DGEN_MODELS", os.path.join(RAIZ, "modelos"))

import torch
from PIL import Image

# qualidade -> (passos de inferencia, resolucao da grade do octree)
QUALIDADES = {
    "Rápida": (5, 256),
    "Equilibrada": (5, 380),
    "Detalhada": (8, 512),
}

_pipe = None
_rembg = None
_lock = threading.Lock()

def carregar():
    global _pipe
    with _lock:
        if _pipe is None:
            from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
            t = time.time()
            _pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
                "tencent/Hunyuan3D-2", subfolder="hunyuan3d-dit-v2-0-turbo", use_safetensors=True)
            _pipe.enable_flashvdm()
            print(f"[gerador] modelo carregado em {time.time() - t:.0f}s", flush=True)
    return _pipe

def tem_fundo(img):
    """True se a imagem nao tem transparencia util (precisa remover o fundo)"""
    return img.mode != "RGBA" or img.getchannel("A").getextrema()[0] == 255

def remover_fundo(img):
    global _rembg
    if _rembg is None:
        from hy3dgen.rembg import BackgroundRemover
        _rembg = BackgroundRemover()
    return _rembg(img.convert("RGB"))

def gerar(img, qualidade="Equilibrada", semente=1234, remover="Automático"):
    """img (PIL) -> (imagem_usada RGBA, trimesh)"""
    pipe = carregar()
    if remover == "Sim" or (remover == "Automático" and tem_fundo(img)):
        img = remover_fundo(img)
    img = img.convert("RGBA")
    passos, octree = QUALIDADES[qualidade]
    from hy3dgen.shapegen import FloaterRemover, DegenerateFaceRemover
    with _lock:
        mesh = pipe(image=img, num_inference_steps=passos, octree_resolution=octree, num_chunks=200000,
                    generator=torch.manual_seed(int(semente)), output_type="trimesh")[0]
    mesh = FloaterRemover()(mesh)          # remove pedacinhos soltos
    mesh = DegenerateFaceRemover()(mesh)
    return img, mesh
