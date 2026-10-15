# -*- coding: utf-8 -*-
"""
Geracao imagem -> malha 3D com os modelos ABERTOS da Tencent, rodando NESTE computador.

- Hunyuan3D-2.1 (3,3 bi parametros): melhor qualidade aberta. Nao cabe inteiro em 8 GB de video,
  entao fica na memoria RAM e cada parte (condicionador -> modelo -> VAE) sobe para a placa so
  quando e usada (accelerate cpu_offload). ~3 min por modelo.
- Hunyuan3D-2.0 turbo: rapido (~10 s), qualidade menor. Bom para testar ideias.

So um modelo fica carregado por vez (os dois juntos nao cabem na placa de 8 GB).
Licenca dos pesos: Tencent Hunyuan 3D 2.0 / 2.1 Community License.
"""
import gc
import os
import sys
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HY3DGEN_MODELS", os.path.join(RAIZ, "modelos"))
sys.path.insert(0, os.path.join(RAIZ, "vendor", "Hunyuan3D-2.1", "hy3dshape"))

import torch
from PIL import Image

# nome na interface -> (motor, passos, resolucao do octree)
QUALIDADES = {
    "Alta (≈3 min)": ("v21", 50, 384),
    "Máxima (≈6 min)": ("v21", 50, 512),
    "Rápida (≈15 s, rascunho)": ("v20", 5, 380),
}
PADRAO = "Alta (≈3 min)"

_motor = None          # "v21" | "v20"
_pipe = None
_rembg = None
_lock = threading.Lock()

def _descarregar():
    global _pipe, _motor
    if _pipe is not None:
        hooks = getattr(_pipe, "_all_hooks", [])
        for h in hooks:
            try:
                h.offload()
                h.remove()
            except Exception:
                pass
        _pipe = None
        _motor = None
        gc.collect()
        torch.cuda.empty_cache()

def carregar(motor="v21"):
    global _pipe, _motor
    with _lock:
        if _motor == motor and _pipe is not None:
            return _pipe
        _descarregar()
        t = time.time()
        if motor == "v21":
            from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline as P21
            pipe = P21.from_pretrained("tencent/Hunyuan3D-2.1", device="cpu")
            # o metodo herdado do diffusers espera 'components'; sequencia: conditioner -> model -> vae
            pipe.components = {"conditioner": pipe.conditioner, "model": pipe.model, "vae": pipe.vae}
            pipe.enable_model_cpu_offload()
            pipe.device = torch.device("cuda")      # tensores nascem na GPU; modulos sobem sob demanda
        else:
            from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline as P20
            pipe = P20.from_pretrained("tencent/Hunyuan3D-2", subfolder="hunyuan3d-dit-v2-0-turbo",
                                       use_safetensors=True)
            pipe.enable_flashvdm()
        _pipe, _motor = pipe, motor
        print(f"[gerador] {motor} carregado em {time.time() - t:.0f}s", flush=True)
        return pipe

def tem_fundo(img):
    """True se a imagem nao tem transparencia util (precisa remover o fundo)"""
    return img.mode != "RGBA" or img.getchannel("A").getextrema()[0] == 255

def remover_fundo(img):
    global _rembg
    if _rembg is None:
        from hy3dgen.rembg import BackgroundRemover
        _rembg = BackgroundRemover()
    return _rembg(img.convert("RGB"))

def gerar(img, qualidade=PADRAO, semente=1234, remover="Automático"):
    """img (PIL) -> (imagem_usada RGBA, trimesh)"""
    motor, passos, octree = QUALIDADES[qualidade]
    pipe = carregar(motor)
    if remover == "Sim" or (remover == "Automático" and tem_fundo(img)):
        img = remover_fundo(img)
    img = img.convert("RGBA")
    from hy3dgen.shapegen import FloaterRemover, DegenerateFaceRemover
    with _lock:
        kw = dict(image=img, num_inference_steps=passos, octree_resolution=octree,
                  generator=torch.manual_seed(int(semente)), output_type="trimesh")
        if motor == "v21":
            mesh = pipe(guidance_scale=5.0, num_chunks=8000, **kw)[0]
        else:
            mesh = pipe(num_chunks=200000, **kw)[0]
    mesh = FloaterRemover()(mesh)          # remove pedacinhos soltos
    mesh = DegenerateFaceRemover()(mesh)
    return img, mesh
