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
ultimo_motor = None    # motor que gerou a ultima malha (define a orientacao no Blender)
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

def _aspecto_imagem(img):
    import numpy as np
    a = np.array(img.convert("RGBA"))[..., 3]
    ys, xs = np.where(a > 128)
    if len(xs) == 0:
        return None
    return (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)

def falhou(mesh, img=None):
    """A IA as vezes devolve uma 'laje' ou um 'cartao chapado' em vez do objeto.
    Teste (validado em 7 casos): a silhueta FRONTAL da malha (largura z / altura y, coordenadas
    glTF) tem que ter proporcao parecida com a do objeto na imagem (fator ate 2).
    Ex.: Cebolinha no 2.1 deu 0,14-0,28 contra 0,85 da imagem; Homer 2.1 deu 0,39 contra 0,35."""
    if mesh is None or len(mesh.faces) < 1000:
        return True
    e = mesh.extents
    if sum(1 for v in e if v > 1.97) >= 2:           # laje ocupando a caixa inteira
        return True
    ai = _aspecto_imagem(img) if img is not None else None
    if ai:
        razao = (e[2] / e[1]) / ai
        if not 0.5 <= razao <= 2.0:
            return True
    return False

def _rodar(motor, img, passos, octree, semente, guidance):
    pipe = carregar(motor)
    with _lock:
        kw = dict(image=img, num_inference_steps=passos, octree_resolution=octree,
                  generator=torch.manual_seed(int(semente)), output_type="trimesh")
        if motor == "v21":
            return pipe(guidance_scale=guidance, num_chunks=8000, **kw)[0]
        return pipe(num_chunks=200000, **kw)[0]

def gerar(img, qualidade=PADRAO, semente=1234, remover="Automático", aviso=None):
    """img (PIL) -> (imagem_usada RGBA, trimesh, nota).
    Se a IA falhar (placas), tenta outra semente e, no 2.1, cai para o 2.0 como ultimo recurso."""
    motor, passos, octree = QUALIDADES[qualidade]
    if remover == "Sim" or (remover == "Automático" and tem_fundo(img)):
        img = remover_fundo(img)
    img = img.convert("RGBA")
    s = int(semente)
    if motor == "v21":
        # trocar a semente nao salvou o 2.1 nos testes (4/4 falharam no Cebolinha): cai direto para o 2.0
        tentativas = [("v21", passos, octree, s, 5.0), ("v20", 8, 512, s, 0), ("v20", 8, 512, s + 1, 0)]
    else:
        tentativas = [("v20", passos, octree, s, 0), ("v20", passos, octree, s + 1, 0)]
    nota = ""
    mesh = None
    for i, (m, p, o, sem, g) in enumerate(tentativas):
        if i and aviso:
            aviso(f"A IA errou a forma; tentando de novo ({i + 1}/{len(tentativas)})...")
        mesh = _rodar(m, img, p, o, sem, g)
        print(f"[gerador] tentativa {i + 1}: {m} semente {sem} -> caixa {mesh.extents.round(2).tolist()}", flush=True)
        if not falhou(mesh, img):
            if i:
                nota = (f"A primeira tentativa falhou; deu certo na tentativa {i + 1} "
                        f"(modelo {'2.1' if m == 'v21' else '2.0'}, semente {sem}).")
            break
    else:
        nota = "⚠️ A IA não conseguiu montar a forma desta imagem. Tente outra imagem (mais 'volume', de frente)."
    from hy3dgen.shapegen import FloaterRemover, DegenerateFaceRemover
    mesh = FloaterRemover()(mesh)          # remove pedacinhos soltos
    mesh = DegenerateFaceRemover()(mesh)
    # partes pequenas desconectadas (ex.: orelha solta no ar) viram lixo na impressao: descarta < 5%
    partes = mesh.split(only_watertight=False)
    if len(partes) > 1:
        maior = max(len(p.faces) for p in partes)
        manter = [p for p in partes if len(p.faces) >= 0.05 * maior]
        if len(manter) < len(partes):
            import trimesh
            print(f"[gerador] {len(partes) - len(manter)} parte(s) pequena(s) solta(s) descartada(s)", flush=True)
            mesh = trimesh.util.concatenate(manter)
    global ultimo_motor
    ultimo_motor = m
    return img, mesh, nota
