# -*- coding: utf-8 -*-
"""
Gera bambu_cfg/*.json a partir dos perfis OFICIAIS instalados no Bambu Studio,
resolvendo 'inherits' E 'include' (os templates de G-code da maquina).

v1 tinha um bug grave: ignorava 'include', e o G-code de inicio/fim/troca vinha
de um perfil pai generico (movimentos ate Y265, fora da mesa da A1 mini).
Este script FALHA se o G-code resultante for diferente do template oficial.

Uso:  python bambu_perfis.py
"""
import glob, json, os, sys

BBL = r"C:\Program Files\Bambu Studio\resources\profiles\BBL"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bambu_cfg")

MACHINE = "Bambu Lab A1 mini 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL A1M"
FILAMENT = "Bambu PLA Basic @BBL A1M"
BED = "Textured PEI Plate"            # mesa instalada (confirmar na impressora!)
FILAMENTS = [("f1.json", "#B01515"),  # 1 vermelho
             ("f2.json", "#111111"),  # 2 preto
             ("f3.json", "#A6A9AD"),  # 3 prata
             ("f4.json", "#F4F4F0")]  # 4 branco
GCODE_KEYS = ["machine_start_gcode", "machine_end_gcode", "layer_change_gcode",
              "time_lapse_gcode", "change_filament_gcode"]

idx = {}
for sub in ("machine", "process", "filament"):
    for f in glob.glob(os.path.join(BBL, sub, "**", "*.json"), recursive=True):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if "name" in d:
            idx[(sub, d["name"])] = d

def resolve(sub, name):
    d = dict(idx[(sub, name)])
    if d.get("inherits"):
        base = resolve(sub, d["inherits"])
        base.update(d)
        d = base
    for inc in d.get("include", []) or []:
        tpl = idx[(sub, inc)]
        for k, v in tpl.items():
            if k not in ("name", "instantiation", "type", "from", "inherits"):
                d[k] = v
    return d

def clean(d):
    d = dict(d)
    for k in ("inherits", "include"):
        d.pop(k, None)
    d["from"] = "system"
    return d

def main():
    os.makedirs(OUT, exist_ok=True)
    machine = clean(resolve("machine", MACHINE))
    process = clean(resolve("process", PROCESS))
    process["curr_bed_type"] = BED
    filament = clean(resolve("filament", FILAMENT))

    # ---- checagens: G-code tem que ser identico ao template oficial da A1 mini
    erros = []
    for k in GCODE_KEYS:
        tpl = idx.get(("machine", f"{MACHINE} template {k}"))
        if tpl is None:
            erros.append(f"template oficial ausente: {k}")
        elif machine.get(k) != tpl[k]:
            erros.append(f"{k} diferente do template oficial")
    if machine.get("printable_area") != ["0x0", "180x0", "180x180", "0x180"]:
        erros.append("printable_area nao e 180x180")
    if erros:
        sys.exit("FALHOU:\n  " + "\n  ".join(erros))

    json.dump(machine, open(os.path.join(OUT, "machine.json"), "w", encoding="utf-8"), indent=1)
    json.dump(process, open(os.path.join(OUT, "process.json"), "w", encoding="utf-8"), indent=1)
    for fn, col in FILAMENTS:
        f = dict(filament)
        f["filament_colour"] = [col]
        json.dump(f, open(os.path.join(OUT, fn), "w", encoding="utf-8"), indent=1)

    ver = "?"
    try:
        ver = json.load(open(os.path.join(BBL, "..", "BBL.json"), encoding="utf-8")).get("version", "?")
    except Exception:
        pass
    print(f"OK perfis gerados (BBL profiles {ver}): {MACHINE} | {PROCESS} | {FILAMENT} x4 | mesa {BED}")
    print("   G-code de maquina identico aos templates oficiais:", ", ".join(GCODE_KEYS))


if __name__ == "__main__":
    main()
