# CLAUDE.md — Imagens em Modelo 3D

Plataforma local: **imagem → malha 3D (Hunyuan3D-2) → peça imprimível (Blender) → .3mf verificado (Bambu Studio)** para a Bambu Lab A1 mini.

A usuária final não é programadora. A interface é em português e deve continuar simples. Responda e documente em **português do Brasil**.

Projeto irmão: [Impress-o3D_Carros](https://github.com/Buenobim/Impress-o3D_Carros). O validador de STL, os perfis da Bambu e a verificação do G-code vieram de lá; correções nessas partes valem para os dois projetos.

## Mapa

- **`app/plataforma.py`:** interface Gradio 5.
  - funções `gerar_tudo` e `refazer_impressao`, e a aba "Meus modelos";
  - cada trabalho vai para `trabalhos/<data>_<nome>/`.
- **`app/gerador.py`:** dois motores, **um carregado por vez** (os dois juntos não cabem em 8 GB).
  - **2.1** (`vendor/Hunyuan3D-2.1/hy3dshape`, pelo `sys.path`): qualidade Alta 50/384 e Máxima 50/512 (passos/octree). Carrega na CPU, define `pipe.components = {conditioner, model, vae}` (o método herdado do diffusers espera isso), chama `enable_model_cpu_offload()` e depois `pipe.device = cuda`. Pico de 6,9 GB, ~3 min.
  - **2.0 turbo** (`hy3dgen`, instalado com `pip -e`): Rápida 5/380, ~15 s.
  - `HY3DGEN_MODELS` aponta para `modelos/`.
- **`app/impressao.py`:** roda `blender/pos_processar.py` (subprocesso, `--python-exit-code 1`) e depois `impressao/fatiar_modelo.py`.
- **`blender/pos_processar.py`:** recebe um JSON de parâmetros e faz:
  1. escala em mm;
  2. remalha por **voxel** (sólido fechado garantido);
  3. decimação;
  4. corte da base plana e pedestal (booleano Manifold);
  5. limpeza (fundir vértices a menos de 2e-4, girar lascas de área zero);
  6. **validação do STL reaberto** (se falhar, refaz por voxel; se falhar de novo, o processo para);
  7. prévias.
- **`impressao/fatiar_modelo.py`:**
  - fatia numa pasta temporária curta, com suporte em árvore, brim automático e sem torre;
  - confere o start G-code oficial (334/334), `M190 S65` e as trajetórias dentro de 180 mm.
- **`impressao/bambu_perfis.py`:** perfis oficiais da A1 mini, resolvendo `inherits` **e** `include`.

## Regras (aprendidas)

**Dependências fixadas** (`requirements.txt`, testadas juntas):
- `transformers <5`: a 5.x renomeia as camadas do DINOv2 e os pesos não carregam ("Missing key ... q_proj").
- Isso obriga `huggingface_hub <1`, `diffusers <0.36` e `gradio 5.x`.
- `rembg 2.0.69` com `pillow 11` (o Gradio 5 exige Pillow <12).
- Remova `hf-gradio` se aparecer.
- Não atualize nada sem testar `scripts/teste_geracao.py` e a interface.

**Modelos:**
- Baixe só o necessário com `scripts/baixar_modelo.py`:
  - `turbo`: DiT + VAE turbo em safetensors;
  - `v21`: `hunyuan3d-dit-v2-1/model.fp16.ckpt`, que já inclui o VAE.
- O carregador oficial baixaria a subpasta inteira, com o `.ckpt` duplicado.
- O 2.1 precisa de `timm`.
- O repositório do 2.1 tem dados de treino com nomes longos demais para o Windows: clone com sparse-checkout sem `hy3dshape/tools/` e sem `hy3dpaint/` (veja `instalar.ps1`).
- Modelos fechados (2.5/3.0, os do site da Tencent) não estão disponíveis; o 2.1 é o melhor aberto.
- O Hunyuan entrega o modelo olhando para −X. O `pos_processar.py` gira 90° em Z para a frente ficar em −Y (nomes das prévias).

**Placa de 8 GB:**
- Só geração de **forma**, com pico de ~6,9 GB no 2.1 (com descarga para a CPU). A textura (paint) pede mais memória; não habilite.
- A geração usa um `Lock`; a fila do Gradio tem concorrência 1.

**Blender:**
- Caminhos **absolutos** no script: caminho relativo de render/import resolve em outro lugar.
- Sempre com `--python-exit-code 1`.
- Booleanos com o solver `MANIFOLD`.
- Nunca entregar STL sem passar por `validate_stl`.

**Windows:**
- Caminhos acima de 260 caracteres quebram o Bambu Studio; por isso o fatiamento roda num temporário curto.
- O disco do computador de teste está quase cheio. `pip --no-cache-dir` e nada de duplicar modelos no cache do Hugging Face.

**Honestidade:**
- Tempo e filamento são **estimativas** do fatiador.
- Diga quando algo foi testado só digitalmente.
- A licença da Tencent pede que conteúdo gerado por IA mostrado publicamente seja identificado (o resumo da interface já mostra o aviso).

## Testar depois de mudar algo

```powershell
.venv\Scripts\python scripts\teste_geracao.py exemplos\gol_render.png   # IA sozinha
iniciar.bat                                                               # interface completa
```

Teste de ponta a ponta sem clicar (com a plataforma aberta):
`gradio_client.Client("http://127.0.0.1:7860/").predict(handle_file(img), nome, "Alta (≈3 min)", 1234, False, "Automático", 60, "Maior lado", 0.6, "Redondo", "1 · Vermelho", True, "Fina (0,12 mm)", api_name="/gerar_tudo")`

## Ideias para próximas versões

- **Várias cores:** segmentar a malha pelas cores da imagem e gerar um 3MF multicor para o AMS.
- **Variações:** várias sementes de uma vez, mostrando as opções lado a lado para escolher.
- **Peça oca** com furo de dreno (economia de filamento em peças grandes).
- **Modelo mini** (`baixar_modelo.py mini`) como opção mais rápida.
- **Hunyuan3D-2.1:** precisaria de 10 GB de vídeo.
