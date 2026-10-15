# -*- coding: utf-8 -*-
"""
Imagens em Modelo 3D - plataforma local (roda neste computador, sem internet depois de instalada).
Imagem -> modelo 3D (Hunyuan3D-2) -> peca imprimivel (Blender) -> arquivo pronto para a A1 mini.

Iniciar:  iniciar.bat   (ou  .venv\\Scripts\\python app\\plataforma.py)
"""
import datetime
import json
import os
import random
import re
import shutil
import sys
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
TRABALHOS = os.path.join(RAIZ, "trabalhos")
os.makedirs(TRABALHOS, exist_ok=True)

import gradio as gr
import gerador
import impressao

AVISO_IA = "Modelo 3D gerado por IA (Hunyuan3D, Tencent, modelo aberto) a partir de imagem."

def _slug(txt):
    txt = re.sub(r"[^A-Za-z0-9_-]+", "_", (txt or "").strip())[:30].strip("_")
    return txt or "modelo"

def _resumo(info, fat):
    v = info["validacao"]
    d = info["dimensoes_mm"]
    linhas = [
        f"**Tamanho:** {d[0]:.0f} × {d[1]:.0f} × {d[2]:.0f} mm  ·  **Volume:** {info['volume_cm3']} cm³",
        f"**Malha:** {'✅ sólido fechado, pronto para imprimir' if v['ok'] else '❌ problema na malha'} "
        f"({format(v['triangulos'], ',').replace(',', '.')} triângulos)",
        f"**Impressão (estimativa do Bambu Studio):** {fat['tempo_estimado']} · {fat['filamento_g']:.0f} g de filamento"
        + (" · com suporte" if fat["suporte"] else " · sem suporte"),
        f"**Conferência do arquivo:** {'✅ perfil oficial da A1 mini, mesa texturizada' if fat['status'] == 'ok' else '❌ ' + '; '.join(fat['erros'])}",
        f"<small>{AVISO_IA}</small>",
    ]
    return "\n\n".join(linhas)

def _arquivos(pasta):
    out = []
    for n in ("modelo_A1mini.3mf", "modelo.stl", "ia.glb"):
        p = os.path.join(pasta, n)
        if os.path.exists(p):
            out.append(p)
    return out

def _previas(pasta):
    return [os.path.join(pasta, f"previa_{n}.png") for n in ("tres_quartos", "frente", "costas")
            if os.path.exists(os.path.join(pasta, f"previa_{n}.png"))]

# ---------------------------------------------------------------------------
def gerar_tudo(img, nome, qualidade, semente, aleatoria, remover,
               tamanho, medida, corte, pedestal, cor, suporte, camada, progress=gr.Progress()):
    if img is None:
        raise gr.Error("Envie uma imagem primeiro.")
    if aleatoria:
        semente = random.randint(0, 999999)
    pasta = os.path.join(TRABALHOS, datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + _slug(nome))
    os.makedirs(pasta)
    img.save(os.path.join(pasta, "entrada.png"))
    progress(0.05, desc="Carregando a IA (só demora na primeira vez ou ao trocar a qualidade)...")
    gerador.carregar(gerador.QUALIDADES[qualidade][0])
    progress(0.25, desc=f"Criando o modelo 3D a partir da imagem ({qualidade.split('(')[-1].rstrip(')')})...")
    usada, mesh, nota = gerador.gerar(img, qualidade, semente, remover,
                                      aviso=lambda m: progress(0.4, desc=m))
    usada.save(os.path.join(pasta, "sem_fundo.png"))
    glb = os.path.join(pasta, "ia.glb")
    mesh.export(glb)
    json.dump(dict(nome=nome, qualidade=qualidade, semente=int(semente), remover_fundo=remover, nota=nota,
                   motor=gerador.ultimo_motor),
              open(os.path.join(pasta, "geracao.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    progress(0.55, desc="Preparando para impressão (Blender + Bambu Studio)...")
    try:
        info, fat = impressao.preparar(pasta, glb, tamanho, medida, corte, pedestal, cor, suporte, camada)
    except Exception as e:
        raise gr.Error(f"O modelo 3D foi criado, mas a preparação para impressão falhou: {e}"[:600])
    resumo = (f"**{nota}**\n\n" if nota else "") + _resumo(info, fat)
    return (usada, glb, _previas(pasta), _arquivos(pasta), resumo, pasta,
            gr.update(value=int(semente)))

def refazer_impressao(pasta, tamanho, medida, corte, pedestal, cor, suporte, camada, progress=gr.Progress()):
    if not pasta or not os.path.exists(os.path.join(pasta, "ia.glb")):
        raise gr.Error("Gere (ou abra) um modelo primeiro.")
    progress(0.2, desc="Refazendo a preparação para impressão...")
    try:
        info, fat = impressao.preparar(pasta, os.path.join(pasta, "ia.glb"), tamanho, medida, corte, pedestal, cor,
                                       suporte, camada)
    except Exception as e:
        raise gr.Error(f"A preparação para impressão falhou: {e}"[:600])
    return _previas(pasta), _arquivos(pasta), _resumo(info, fat)

def listar_trabalhos():
    itens = []
    for d in sorted(os.listdir(TRABALHOS), reverse=True):
        p = os.path.join(TRABALHOS, d)
        prev = os.path.join(p, "previa_tres_quartos.png")
        if os.path.isdir(p) and os.path.exists(prev):
            itens.append((prev, d))
    return itens

def abrir_trabalho(evt: gr.SelectData):
    d = listar_trabalhos()[evt.index][1]
    pasta = os.path.join(TRABALHOS, d)
    resumo = ""
    try:
        info = json.load(open(os.path.join(pasta, "impressao.json"), encoding="utf-8"))
        fat = json.load(open(os.path.join(pasta, "fatiamento.json"), encoding="utf-8"))
        resumo = _resumo(info, fat)
    except Exception:
        pass
    glb = os.path.join(pasta, "ia.glb")
    return (pasta, glb if os.path.exists(glb) else None, _previas(pasta), _arquivos(pasta), resumo)

def abrir_pasta(pasta):
    if pasta and os.path.isdir(pasta):
        os.startfile(pasta)

# ---------------------------------------------------------------------------
CSS = ".gradio-container {max-width: 1280px !important} footer {display:none !important}"

with gr.Blocks(title="Imagens em Modelo 3D", theme=gr.themes.Soft(primary_hue="rose"), css=CSS) as app:
    pasta_atual = gr.State("")
    gr.Markdown("# 🧩 Imagens em Modelo 3D\nEnvie uma imagem, escolha o tamanho e receba o arquivo pronto "
                "para imprimir na **A1 mini**. Tudo roda neste computador.")
    with gr.Tab("Criar modelo"):
        with gr.Row():
            with gr.Column(scale=1):
                img = gr.Image(label="Imagem", type="pil", image_mode="RGBA", sources=["upload", "clipboard"], height=300)
                nome = gr.Textbox(label="Nome do modelo", placeholder="ex.: pinguim da Ana")
                with gr.Accordion("Geração (IA)", open=True):
                    qualidade = gr.Radio(list(gerador.QUALIDADES), value=gerador.PADRAO, label="Qualidade",
                                         info="Alta e Máxima usam o modelo Hunyuan3D-2.1 (melhor); Rápida usa o 2.0 (rascunho)")
                    remover = gr.Radio(["Automático", "Sim", "Não"], value="Automático", label="Remover o fundo da imagem")
                    with gr.Row():
                        semente = gr.Number(value=1234, precision=0, label="Semente (mesma semente = mesmo resultado)")
                        aleatoria = gr.Checkbox(value=False, label="Sortear semente")
                with gr.Accordion("Impressão", open=True):
                    tamanho = gr.Slider(15, 170, value=80, step=1, label="Tamanho (mm)")
                    medida = gr.Radio(["Altura", "Maior lado"], value="Altura", label="O tamanho vale para")
                    corte = gr.Slider(0, 3, value=0.6, step=0.1, label="Base plana: cortar embaixo (mm)")
                    pedestal = gr.Radio(list(impressao.PEDESTAIS), value="Sem pedestal", label="Pedestal (ajuda peças com apoio pequeno)")
                    cor = gr.Dropdown(list(impressao.CORES), value="1 · Vermelho", label="Cor (slot do AMS)")
                    suporte = gr.Checkbox(value=True, label="Suporte automático (recomendado para bonecos e esculturas)")
                    camada = gr.Radio(list(impressao.CAMADAS), value="Padrão (0,20 mm)", label="Camada")
                gerar_btn = gr.Button("✨ Gerar modelo 3D", variant="primary", size="lg")
                refazer_btn = gr.Button("↻ Só refazer a impressão (mudou tamanho/base/cor)")
            with gr.Column(scale=2):
                with gr.Row():
                    sem_fundo = gr.Image(label="Imagem usada (sem fundo)", height=260, interactive=False)
                    modelo_ia = gr.Model3D(label="Modelo 3D (gire com o mouse)", height=260, clear_color=(0.94, 0.93, 0.91, 1))
                previas = gr.Gallery(label="Peça pronta para imprimir", columns=3, height=300, object_fit="contain")
                resumo = gr.Markdown()
                arquivos = gr.File(label="Arquivos (o .3mf abre direto no Bambu Studio)", file_count="multiple")
                abrir_btn = gr.Button("📂 Abrir a pasta deste modelo")
    with gr.Tab("Meus modelos"):
        galeria = gr.Gallery(label="Clique para abrir", columns=5, height=520, object_fit="contain")
        atualizar = gr.Button("Atualizar lista")
        gr.Markdown("Ao clicar num modelo, ele abre na aba **Criar modelo** (dá para refazer a impressão com outro tamanho).")
    with gr.Tab("Dicas"):
        gr.Markdown(open(os.path.join(AQUI, "dicas.md"), encoding="utf-8").read())

    entradas_imp = [tamanho, medida, corte, pedestal, cor, suporte, camada]
    gerar_btn.click(gerar_tudo, [img, nome, qualidade, semente, aleatoria, remover] + entradas_imp,
                    [sem_fundo, modelo_ia, previas, arquivos, resumo, pasta_atual, semente])
    refazer_btn.click(refazer_impressao, [pasta_atual] + entradas_imp, [previas, arquivos, resumo])
    abrir_btn.click(abrir_pasta, [pasta_atual], None)
    atualizar.click(listar_trabalhos, None, galeria)
    app.load(listar_trabalhos, None, galeria)
    galeria.select(abrir_trabalho, None, [pasta_atual, modelo_ia, previas, arquivos, resumo])

if __name__ == "__main__":
    threading.Thread(target=gerador.carregar, daemon=True).start()   # ja carrega a IA em segundo plano
    app.queue(default_concurrency_limit=1).launch(server_name="127.0.0.1", server_port=7860, inbrowser=True,
                                                  allowed_paths=[TRABALHOS], show_error=True)
