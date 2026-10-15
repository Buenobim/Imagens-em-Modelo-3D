# -*- coding: utf-8 -*-
"""Teste do Hunyuan3D-2.1 (forma) numa placa de 8 GB: modelo na CPU e partes sobem para a GPU sob demanda."""
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HY3DGEN_MODELS", os.path.join(RAIZ, "modelos"))
sys.path.insert(0, os.path.join(RAIZ, "vendor", "Hunyuan3D-2.1", "hy3dshape"))

import torch
from PIL import Image
from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline

img_path, out = sys.argv[1], sys.argv[2]
passos = int(sys.argv[3]) if len(sys.argv) > 3 else 50
octree = int(sys.argv[4]) if len(sys.argv) > 4 else 384

t0 = time.time()
DT = torch.bfloat16 if os.environ.get("DTYPE") == "bf16" else torch.float16
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2.1", device="cpu", dtype=DT)
# o metodo copiado do diffusers espera 'components'; a sequencia ja vem definida (conditioner->model->vae)
pipe.components = {"conditioner": pipe.conditioner, "model": pipe.model, "vae": pipe.vae}
pipe.enable_model_cpu_offload()
pipe.device = torch.device("cuda")          # tensores nascem na GPU; os modulos sobem sob demanda
print(f"[v21] carregado em {time.time() - t0:.0f}s", flush=True)

img = Image.open(img_path).convert("RGBA")
torch.cuda.reset_peak_memory_stats()
t1 = time.time()
mesh = pipe(image=img, num_inference_steps=passos, octree_resolution=octree, num_chunks=8000,
            guidance_scale=float(os.environ.get("GUIDANCE", "5.0")), generator=torch.manual_seed(int(os.environ.get("SEMENTE", "1234"))), output_type="trimesh")[0]
print(f"[v21] {passos} passos, octree {octree}: {time.time() - t1:.0f}s | {len(mesh.faces)} faces | "
      f"pico VRAM {torch.cuda.max_memory_allocated() / 1e9:.2f} GB", flush=True)
mesh.export(out)
