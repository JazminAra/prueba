# -*- coding: utf-8 -*-
"""
CHAVI – Modelo de Optimización de Recursos Hídricos (PuLP)
----------------------------------------------------------
Script ejecutable en cualquier computadora con Python 3.8+ y PuLP.

Instalación (una vez):
    pip install pulp

Ejecución (ejemplos):
    python chavi_pulp_model.py --scenario S1
    python chavi_pulp_model.py --scenario S2 --mult-pozos-chao 1.5 --mult-pozos-viru 1.2
    python chavi_pulp_model.py --penalty 1e8 --cap-santa 88 --out out_run

Genera CSVs en el directorio indicado por --out (default: ./out_chavi):
    - allocations_x.csv  (asignaciones x_ijm y entregado)
    - deficits_u.csv     (déficits u_jm por demanda y mes)
    - summary.json       (estado, objetivo, beneficio, costo, penalidad, déficits por mes)
"""

import os
import csv
import json
import argparse
from math import isfinite

try:
    import pulp as pl
except Exception as e:
    raise SystemExit("ERROR: No se pudo importar PuLP. Instala con: pip install pulp\nDetalle: %s" % e)


def build_and_solve(
    scenario="S1",
    mult_pozos_chao=1.0,
    mult_pozos_viru=1.0,
    penalty_usd_hm3=1e8,
    weight_ptap=100.0,
    weight_ind_pec=50.0,
    weight_agro=1.0,
    cap_santa_m3s=88.0,
    solver_name="cbc",
    solver_time_limit=None,
    solver_msg=False
):
    # -----------------------------
    # Datos base
    # -----------------------------
    months = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    days = [31,28,31,30,31,30,31,31,30,31,30,31]
    secs = {m: d*24*3600 for m, d in zip(months, days)}  # segundos por mes

    sources = [
        "Santa","Huamanzaña","Chorobal","Viru_Rio",
        "Dren_Chao","Dren_Viru","Pozos_Chao","Pozos_Viru"
    ]

    demands = [
        "Chao","Viru","S1","S2","S3","S4","PTAP_Trujillo","PTAP_Chao","Industria","Pecuario"
    ]

    offer_m3s = {
        "Santa":       [17.59, 18.41, 17.29, 16.54, 16.36, 14.90, 11.72, 11.90, 11.55, 14.72, 18.06, 19.02],
        "Huamanzaña":  [0.00]*12,
        "Chorobal":    [0.00, 0.00, 0.00, 0.01, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        "Viru_Rio":    [0.21, 1.15, 2.01, 1.89, 0.57, 0.07, 0.03, 0.00, 0.00, 0.00, 0.00, 0.00],
        "Dren_Chao":   [0.53, 0.66, 0.50, 0.51, 0.52, 0.49, 0.49, 0.67, 0.94, 1.04, 1.04, 0.83],
        "Dren_Viru":   [0.61, 0.70, 0.63, 0.69, 0.62, 0.62, 0.57, 0.59, 0.59, 0.53, 0.65, 0.65],
        "Pozos_Chao":  [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.19, 0.22, 0.27, 0.24, 0.00, 0.00],
        "Pozos_Viru":  [0.00, 0.00, 0.00, 0.00, 0.00, 0.15, 0.19, 0.22, 0.25, 0.23, 0.25, 0.19],
    }

    demand_m3s = {
        "Chao":          [1.98, 1.82, 1.92, 1.88, 1.85, 1.79, 1.74, 2.72, 3.77, 4.16, 3.80, 3.14],
        "Viru":          [2.35, 2.76, 2.78, 2.99, 3.18, 3.15, 2.78, 2.93, 2.66, 2.77, 2.64, 3.22],
        "S1":            [4.60, 4.73, 4.49, 4.45, 3.98, 3.70, 2.88, 2.89, 2.99, 3.45, 4.31, 4.47],
        "S2":            [0.92, 0.94, 0.90, 0.89, 0.79, 0.74, 0.57, 0.58, 0.60, 0.69, 0.86, 0.89],
        "S3":            [2.83, 2.91, 2.77, 2.74, 2.45, 2.27, 1.77, 1.78, 1.84, 2.12, 2.65, 2.75],
        "S4":            [3.18, 3.27, 3.11, 3.08, 2.75, 2.56, 1.99, 2.00, 2.07, 2.39, 2.98, 3.09],
        "PTAP_Trujillo": [1.22, 1.14, 1.21, 1.11, 1.17, 1.18, 1.00, 1.11, 1.20, 1.23, 1.19, 1.21],
        "PTAP_Chao":     [0.04, 0.04, 0.03, 0.04, 0.04, 0.04, 0.04, 0.03, 0.04, 0.04, 0.04, 0.04],
        "Industria":     [0.50]*12,
        "Pecuario":      [0.60]*12,
    }

    cost_offer_USD_m3 = {
        "Santa":      0.024820,
        "Huamanzaña": 0.0017953,
        "Chorobal":   0.0017953,
        "Viru_Rio":   0.0018038,
        "Dren_Chao":  0.0017953,
        "Dren_Viru":  0.0018038,
        "Pozos_Chao": 0.0615100,
        "Pozos_Viru": 0.0615100,
    }

    value_dem_USD_m3 = {
        "Chao":          0.0017953,
        "Viru":          0.0018038,
        "S1":            0.024820,
        "S2":            0.024820,
        "S3":            0.024820,
        "S4":            0.024820,
        "PTAP_Trujillo": 0.028915,
        "PTAP_Chao":     0.028915,
        "Industria":     0.024820,
        "Pecuario":      0.024820,
    }

    efficiencies = {
        "S1": {
            "Chao":0.30, "Viru":0.30,
            "S1":0.89, "S2":0.89, "S3":0.89, "S4":0.89,
            "PTAP_Trujillo":1.0, "PTAP_Chao":1.0, "Industria":1.0, "Pecuario":1.0,
        },
        "S2": {
            "Chao":0.60, "Viru":0.60,
            "S1":0.95, "S2":0.95, "S3":0.95, "S4":0.95,
            "PTAP_Trujillo":1.0, "PTAP_Chao":1.0, "Industria":1.0, "Pecuario":1.0,
        }
    }

    # Compatibilidad (arcos permitidos)
    allowed_arcs = set()
    for j in demands:
        for m in months:
            allowed_arcs.add(("Santa", j, m))
    for i in ["Huamanzaña","Chorobal","Dren_Chao","Pozos_Chao"]:
        for m in months:
            allowed_arcs.add((i,"Chao",m))
    for i in ["Viru_Rio","Dren_Viru","Pozos_Viru"]:
        for m in months:
            allowed_arcs.add((i,"Viru",m))

    # Conversión a hm3/mes
    Qhat = {(i,m): offer_m3s[i][mi] * secs[m] / 1e6 for i in sources for mi,m in enumerate(months)}
    def Qhat_adjusted(i, m):
        base = Qhat[(i,m)]
        if i == "Pozos_Chao": return base * mult_pozos_chao
        if i == "Pozos_Viru": return base * mult_pozos_viru
        return base

    Dhat = {(j,m): demand_m3s[j][mi] * secs[m] / 1e6 for j in demands for mi,m in enumerate(months)}
    CapSanta = {m: cap_santa_m3s * secs[m] / 1e6 for m in months}

    cost_offer_USD_hm3 = {i: cost_offer_USD_m3[i]*1e6 for i in sources}
    value_dem_USD_hm3 = {j: value_dem_USD_m3[j]*1e6 for j in demands}

    weight_dem = {}
    for j in demands:
        if j in ["PTAP_Trujillo","PTAP_Chao"]:
            weight_dem[j] = weight_ptap
        elif j in ["Industria","Pecuario"]:
            weight_dem[j] = weight_ind_pec
        else:
            weight_dem[j] = weight_agro

    # -----------------------------
    # Modelo
    # -----------------------------
    prob = pl.LpProblem("CHAVI_Optim_Recursos_Hidricos", pl.LpMaximize)

    # Variables
    x = {(i,j,m): pl.LpVariable(f"x__{i}__{j}__{m}", lowBound=0) for (i,j,m) in allowed_arcs}
    u = {(j,m): pl.LpVariable(f"u__{j}__{m}", lowBound=0) for j in demands for m in months}

    eff = efficiencies[scenario]

    # Balance de demanda
    for j in demands:
        ej = eff[j]
        for m in months:
            prob += (pl.lpSum(x[(i,j,m)] for i in sources if (i,j,m) in x) * ej + u[(j,m)] == Dhat[(j,m)]), f"Balance_Dem_{j}_{m}"

    # Oferta por fuente/mes
    for i in sources:
        for m in months:
            prob += (pl.lpSum(x[(i,j,m)] for j in demands if (i,j,m) in x) <= Qhat_adjusted(i,m)), f"Oferta_{i}_{m}"

    # Capacidad canal Santa
    for m in months:
        prob += (pl.lpSum(x[("Santa", j, m)] for j in demands if ("Santa", j, m) in x) <= CapSanta[m]), f"Cap_Santa_{m}"

    # Déficit cero para PTAPs, Industria, Pecuario
    for j in ["PTAP_Trujillo","PTAP_Chao","Industria","Pecuario"]:
        for m in months:
            prob += (u[(j,m)] == 0), f"DeficitCero_{j}_{m}"

    # Objetivo
    benefit_term = pl.lpSum((eff[j]*value_dem_USD_hm3[j] - cost_offer_USD_hm3[i]) * x[(i,j,m)] for (i,j,m) in x)
    penalty_term = pl.lpSum(penalty_usd_hm3 * weight_dem[j] * u[(j,m)] for j in demands for m in months)
    prob += benefit_term - penalty_term, "Beneficio_Neto"

    # Solver
    solver = None
    solver_name = (solver_name or "cbc").lower()
    try:
        if solver_name in ("cbc","pulp_cbc_cmd"):
            solver = pl.PULP_CBC_CMD(msg=solver_msg, timeLimit=solver_time_limit)
        elif solver_name in ("glpk","glpk_cmd"):
            solver = pl.GLPK_CMD(msg=solver_msg, options=[f'--tmlim {solver_time_limit}'] if solver_time_limit else None)
        else:
            solver = pl.PULP_CBC_CMD(msg=solver_msg, timeLimit=solver_time_limit)
    except Exception:
        solver = None

    if solver is not None:
        prob.solve(solver)
    else:
        prob.solve()  # fallback

    status = pl.LpStatus[prob.status]
    obj = pl.value(prob.objective)

    # Desglose de beneficio, costo y penalidad
    benefit_total, cost_total = 0.0, 0.0
    for (i,j,m), var in x.items():
        val = var.value() or 0.0
        benefit_total += eff[j]*value_dem_USD_hm3[j]*val
        cost_total    += cost_offer_USD_hm3[i]*val
    penalty_total = sum(penalty_usd_hm3 * weight_dem[j] * (u[(j,m)].value() or 0.0) for j in demands for m in months)

    # Armado de resultados
    alloc_rows = []
    for (i,j,m), var in x.items():
        xv = var.value() or 0.0
        delivered = eff[j]*xv
        alloc_rows.append({
            "month": m, "source": i, "demand": j,
            "x_hm3": round(xv, 6),
            "delivered_hm3": round(delivered, 6),
            "cost_USD": round(cost_offer_USD_hm3[i]*xv, 2),
            "benefit_USD": round(value_dem_USD_hm3[j]*delivered, 2)
        })

    deficit_rows = []
    deficits_by_month = {m: 0.0 for m in months}
    for j in demands:
        for m in months:
            uv = u[(j,m)].value() or 0.0
            deficits_by_month[m] += uv
            deficit_rows.append({"demand": j, "month": m, "deficit_hm3": round(uv, 6)})

    summary = {
        "status": status,
        "objective_USD": round(obj if obj is not None else float("nan"), 2),
        "benefit_USD": round(benefit_total, 2),
        "cost_USD": round(cost_total, 2),
        "penalty_USD": round(penalty_total, 2),
        "scenario": scenario,
        "mult_pozos_chao": mult_pozos_chao,
        "mult_pozos_viru": mult_pozos_viru,
        "cap_santa_m3s": cap_santa_m3s,
        "penalty_usd_hm3": penalty_usd_hm3,
        "deficits_hm3_by_month": {m: round(deficits_by_month[m], 6) for m in months},
    }

    return {
        "status": status,
        "objective": obj,
        "benefit_total": benefit_total,
        "cost_total": cost_total,
        "penalty_total": penalty_total,
        "alloc_rows": alloc_rows,
        "deficit_rows": deficit_rows,
        "summary": summary,
    }


def main():
    ap = argparse.ArgumentParser(description="CHAVI – Modelo de Optimización (PuLP)")
    ap.add_argument("--scenario", choices=["S1","S2"], default="S1", help="Escenario de eficiencias (S1 o S2).")
    ap.add_argument("--mult-pozos-chao", type=float, default=1.0, help="Multiplicador de oferta Pozos_Chao.")
    ap.add_argument("--mult-pozos-viru", type=float, default=1.0, help="Multiplicador de oferta Pozos_Viru.")
    ap.add_argument("--penalty", type=float, default=1e8, help="Penalidad (USD/hm3) por déficit ponderado.")
    ap.add_argument("--weight-ptap", type=float, default=100.0, help="Peso de déficit para PTAPs.")
    ap.add_argument("--weight-ind-pec", type=float, default=50.0, help="Peso de déficit para Industria/Pecuario.")
    ap.add_argument("--weight-agro", type=float, default=1.0, help="Peso de déficit para sectores agrícolas.")
    ap.add_argument("--cap-santa", type=float, default=88.0, help="Capacidad del canal Santa (m3/s).")
    ap.add_argument("--solver", choices=["cbc","glpk","auto"], default="cbc", help="Solver a usar (cbc recomendado).")
    ap.add_argument("--time-limit", type=int, default=None, help="Tiempo máx. del solver (segundos).")
    ap.add_argument("--out", default="out_chavi", help="Directorio de salida para CSV/JSON.")
    ap.add_argument("--solver-msg", action="store_true", help="Muestra mensajes del solver.")
    args = ap.parse_args()

    res = build_and_solve(
        scenario=args.scenario,
        mult_pozos_chao=args.mult_pozos_chao,
        mult_pozos_viru=args.mult_pozos_viru,
        penalty_usd_hm3=args.penalty,
        weight_ptap=args.weight_ptap,
        weight_ind_pec=args.weight_ind_pec,
        weight_agro=args.weight_agro,
        cap_santa_m3s=args.cap_santa,
        solver_name=("cbc" if args.solver=="auto" else args.solver),
        solver_time_limit=args.time_limit,
        solver_msg=args.solver_msg
    )

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    # Guardar CSVs
    alloc_path = os.path.join(out_dir, "allocations_x.csv")
    with open(alloc_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["month","source","demand","x_hm3","delivered_hm3","cost_USD","benefit_USD"])
        w.writeheader()
        for row in res["alloc_rows"]:
            w.writerow(row)

    deficit_path = os.path.join(out_dir, "deficits_u.csv")
    with open(deficit_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["demand","month","deficit_hm3"])
        w.writeheader()
        for row in res["deficit_rows"]:
            w.writerow(row)

    summary_path = os.path.join(out_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(res["summary"], f, ensure_ascii=False, indent=2)

    # Resumen por consola
    print("="*70)
    print("Estado:", res["summary"]["status"])
    print("Objetivo (USD):", round(res["summary"]["objective_USD"], 2))
    print("  Beneficio total (USD):", round(res["summary"]["benefit_USD"], 2))
    print("  Costo total (USD):    ", round(res["summary"]["cost_USD"], 2))
    print("  Penalidad (USD):      ", round(res["summary"]["penalty_USD"], 2))
    print("-"*70)
    print("Déficit por mes (hm3):")
    for m, v in res["summary"]["deficits_hm3_by_month"].items():
        print(f"  {m}: {v}")
    print("-"*70)
    print("Archivos generados:")
    print("  ", alloc_path)
    print("  ", deficit_path)
    print("  ", summary_path)
    print("="*70)


if __name__ == "__main__":
    main()
