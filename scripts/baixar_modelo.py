# -*- coding: utf-8 -*-
"""
Baixa SO os arquivos necessarios do modelo Hunyuan3D-2 (geracao de forma) para ./modelos.
(O carregador oficial baixaria a pasta inteira, com .ckpt e .safetensors duplicados.)

Licenca: Tencent Hunyuan 3D 2.0 Community License (ver vendor/Hunyuan3D-2/LICENSE).
Uso: .venv\\Scripts\\python scripts\\baixar_modelo.py [turbo|mini]
"""
import os
import sys
from huggingface_hub import hf_hub_download

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELOS = os.path.join(RAIZ, "modelos")

VARIANTES = {
    # nome: (repo, subpasta do DiT)
    "turbo": ("tencent/Hunyuan3D-2", ["hunyuan3d-dit-v2-0-turbo", "hunyuan3d-vae-v2-0-turbo"]),
    "mini": ("tencent/Hunyuan3D-2mini", ["hunyuan3d-dit-v2-mini-turbo", "hunyuan3d-vae-v2-mini-turbo"]),
    # 2.1: melhor modelo ABERTO (3,3 bi parametros). Pesos em .ckpt (inclui o VAE). ~7,4 GB
    "v21": ("tencent/Hunyuan3D-2.1", ["hunyuan3d-dit-v2-1"]),
}
ARQUIVOS = {"v21": ("config.yaml", "model.fp16.ckpt")}

def baixar(nome="turbo"):
    repo, subs = VARIANTES[nome]
    destino = os.path.join(MODELOS, repo)
    for sub in subs:       # DiT (forma) + VAE turbo (FlashVDM)
        for arq in ARQUIVOS.get(nome, ("config.yaml", "model.fp16.safetensors")):
            caminho = hf_hub_download(repo_id=repo, filename=f"{sub}/{arq}", local_dir=destino)
            print("ok", caminho, round(os.path.getsize(caminho) / 1e9, 2), "GB")

if __name__ == "__main__":
    baixar(sys.argv[1] if len(sys.argv) > 1 else "turbo")
