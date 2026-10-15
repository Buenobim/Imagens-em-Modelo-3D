# -*- coding: utf-8 -*-
"""Teste rapido: imagem -> malha 3D (GLB) com o Hunyuan3D-2 turbo. Mede tempo e memoria de video."""
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HY3DGEN_MODELS", os.path.join(RAIZ, "modelos"))

import torch
from PIL import Image
from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

img_path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(img_path)[0] + "_3d.glb"

t0 = time.time()
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "tencent/Hunyuan3D-2", subfolder="hunyuan3d-dit-v2-0-turbo", use_safetensors=True)
pipe.enable_flashvdm()
print(f"modelo carregado em {time.time() - t0:.1f}s")

img = Image.open(img_path)
precisa_fundo = img.mode != "RGBA" or img.getchannel("A").getextrema()[0] == 255
img = img.convert("RGBA")
if precisa_fundo:
    t1 = time.time()
    img = BackgroundRemover()(img.convert("RGB"))
    print(f"fundo removido em {time.time() - t1:.1f}s")

torch.cuda.reset_peak_memory_stats()
t2 = time.time()
mesh = pipe(image=img, num_inference_steps=5, octree_resolution=380, num_chunks=200000,
            generator=torch.manual_seed(1234), output_type="trimesh")[0]
print(f"malha gerada em {time.time() - t2:.1f}s | {len(mesh.vertices)} vertices, {len(mesh.faces)} faces"
      f" | pico de VRAM {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
mesh.export(out)
print("salvo:", out)
