# -*- coding: utf-8 -*-
"""
Fatia UM modelo (STL) no Bambu Studio por linha de comando, com os perfis OFICIAIS da A1 mini,
e confere o G-code gerado (logica herdada do repositorio Impress-o3D_Carros).

  python impressao/fatiar_modelo.py modelo.stl [--sem-suporte] [--slot 1..4] [--camada 0.12|0.16|0.20]

Retorna/grava <pasta>/fatiamento.json e <nome>_A1mini.3mf ao lado do STL.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile, zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(AQUI, "bambu_cfg")
BAMBU = r"C:\Program Files\Bambu Studio\bambu-studio.exe"
BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL"
BED = 180.0
PROCESSOS = {   # altura de camada -> perfil oficial A1M
    "0.12": "0.12mm Fine @BBL A1M",
    "0.16": "0.16mm Optimal @BBL A1M",
    "0.20": "0.20mm Standard @BBL A1M",
}

def _processo(camada):
    """perfil de processo oficial resolvido (inherits) para a altura de camada pedida"""
    if camada == "0.20":
        return json.load(open(os.path.join(CFG, "process.json"), encoding="utf-8"))
    sys.path.insert(0, AQUI)
    import bambu_perfis as bp
    d = bp.clean(bp.resolve("process", PROCESSOS[camada]))
    d["curr_bed_type"] = bp.BED
    return d

def fatiar(stl, suporte=True, slot=1, camada="0.20"):
    stl = os.path.abspath(stl)
    pasta = os.path.dirname(stl)
    nome = os.path.splitext(os.path.basename(stl))[0]
    out3mf = f"{nome}_A1mini.3mf"
    proc = _processo(camada)
    proc["enable_support"] = "1" if suporte else "0"
    proc["support_type"] = "tree(auto)"
    proc["brim_type"] = "auto_brim"
    proc["enable_prime_tower"] = "0"
    work = os.path.realpath(tempfile.mkdtemp(prefix="i3d_"))   # caminho curto (limite de 260 do Windows)
    try:
        shutil.copy(os.path.join(CFG, "machine.json"), work)
        shutil.copy(os.path.join(CFG, f"f{slot}.json"), os.path.join(work, "fil.json"))
        shutil.copy(stl, os.path.join(work, "modelo.stl"))
        json.dump(proc, open(os.path.join(work, "process.json"), "w", encoding="utf-8"), indent=1)
        cmd = [BAMBU, "--slice", "0", "--arrange", "1", "--orient", "0",
               "--load-settings", "machine.json;process.json", "--load-filaments", "fil.json",
               "--outputdir", ".", "--export-3mf", "saida.3mf", "modelo.stl"]
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, errors="ignore")
        res = os.path.join(work, "saida.3mf")
        if r.returncode != 0 or not os.path.exists(res):
            msg = [l.split("error_message=")[-1] for l in (r.stdout + r.stderr).splitlines() if "error_message" in l]
            raise RuntimeError(f"Fatiamento falhou: {msg[:1] or r.returncode}")
        shutil.copy(res, os.path.join(pasta, out3mf))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    rep = verificar(os.path.join(pasta, out3mf))
    rep.update(arquivo_3mf=out3mf, suporte=suporte, slot=slot, camada_mm=camada)
    json.dump(rep, open(os.path.join(pasta, "fatiamento.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return rep

def verificar(path3mf):
    z = zipfile.ZipFile(path3mf)
    gcode = z.read("Metadata/plate_1.gcode").decode("utf-8", "ignore")
    proj = json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
    erros = []
    tpl = json.load(open(os.path.join(BBL, "machine", "Bambu Lab A1 mini 0.4 nozzle template machine_start_gcode.json"),
                         encoding="utf-8"))["machine_start_gcode"]
    fixed = [l.strip() for l in tpl.splitlines() if l.strip() and not l.strip().startswith(";")
             and "{" not in l and "[" not in l]
    pos = found = 0
    for l in fixed:
        i = gcode.find(l, pos)
        if i >= 0:
            found += 1
            pos = i + len(l)
    if found != len(fixed):
        erros.append("start G-code difere do template oficial da A1 mini")
    if proj.get("printer_model") != "Bambu Lab A1 mini":
        erros.append("printer_model nao e A1 mini")
    beds = sorted(set(re.findall(r"^M190 S(\d+)", gcode, re.M)))
    if beds != ["65"]:
        erros.append(f"temperatura da mesa inesperada: {beds}")
    body = gcode.split("; MACHINE_START_GCODE_END", 1)[-1].split("; MACHINE_END_GCODE_START", 1)[0]
    x = y = None
    absolute = True
    lo, hi = [1e9, 1e9], [-1e9, -1e9]
    for line in body.splitlines():
        s = line.split(";", 1)[0].strip()
        if s == "G90":
            absolute = True
        elif s == "G91":
            absolute = False
        if not re.match(r"G[01]\s", s):
            continue
        mx, my, me = re.search(r"X(-?[\d.]+)", s), re.search(r"Y(-?[\d.]+)", s), re.search(r"E(-?[\d.]+)", s)
        if absolute:
            x = float(mx.group(1)) if mx else x
            y = float(my.group(1)) if my else y
        if me and float(me.group(1)) > 0 and (mx or my) and x is not None and y is not None:
            lo = [min(lo[0], x), min(lo[1], y)]
            hi = [max(hi[0], x), max(hi[1], y)]
    if lo[0] < 0 or lo[1] < 0 or hi[0] > BED or hi[1] > BED:
        erros.append("trajetoria de impressao fora da mesa 180x180")
    t = re.search(r"total estimated time: ([^\n;]+)", gcode)
    w = re.search(r"total filament weight \[g\] : ([^\n]+)", gcode)
    return dict(status="ok" if not erros else "FALHOU", erros=erros,
                start_gcode_oficial=f"{found}/{len(fixed)}", mesa=proj.get("curr_bed_type"),
                trajetorias_xy=[[round(v, 1) for v in lo], [round(v, 1) for v in hi]],
                tempo_estimado=t.group(1).strip() if t else None,
                filamento_g=float(w.group(1).split(",")[0]) if w else None,
                observacao="estimativas do fatiador, nao medicoes")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stl")
    ap.add_argument("--sem-suporte", action="store_true")
    ap.add_argument("--slot", type=int, default=1)
    ap.add_argument("--camada", default="0.20", choices=list(PROCESSOS))
    a = ap.parse_args()
    rep = fatiar(a.stl, suporte=not a.sem_suporte, slot=a.slot, camada=a.camada)
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    sys.exit(0 if rep["status"] == "ok" else 1)
