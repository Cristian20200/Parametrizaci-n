#!/usr/bin/env python3
"""Auditor contractual: anexo Prestador.xlsx vs exportación HAM.xlsx.
No crea/inactiva tecnologías en HAM; solo produce decisiones verificables.
"""
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from homologar import read_xlsx, normalize, similarity

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "resultados"
FIELDS = ["origen","fila_anexo","codigo_anexo","descripcion_anexo","tarifa_anexo",
          "fila_ham","codigo_ham","descripcion_ham","tarifa_ham",
          "similitud_descripcion","diferencia_tarifa","categoria_propuesta",
          "codigo_maestro_propuesto","estado_homologacion_maestro",
          "decision","motivo","accion_ham","requiere_validacion"]

def key(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")

def amount(v):
    v = str(v or "").strip().replace("$", "").replace(" ", "")
    if not v:
        return None
    # Convenciones colombianas: 25.400 -> 25400; 25.400,50 -> 25400.50.
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
    elif "," in v:
        pieces=v.split(",")
        v=v.replace(",", "") if len(pieces[-1]) == 3 else v.replace(",", ".")
    elif "." in v:
        pieces=v.split(".")
        if len(pieces[-1]) == 3 and all(p.isdigit() for p in pieces):
            v=v.replace(".", "")
    try:
        return Decimal(v)
    except InvalidOperation:
        return None

def load_book(name):
    filename=ROOT/name
    if not filename.exists():
        raise FileNotFoundError(name)
    it=enumerate(read_xlsx(filename),1)
    sampled=[]
    for _ in range(25):
        try:sampled.append(next(it))
        except StopIteration:break
    code_words={"codigo","codigo_prestador","codigo_ham","codigo_tecnologia","cod","cups","cums","cum","subcodigo"}
    desc_words={"descripcion","descripcion_prestador","descripcion_ham","descripcion_tecnologia","nombre","nombre_servicio"}
    tariff_words={"tarifa","valor","valor_pactado","valor_parametrizado","precio","valor_contratado"}
    found=None
    for i,row in sampled:
        cols=[key(x) for x in row]
        def locate(variants):
            return next((j for j,x in enumerate(cols) if x in variants),None)
        pos=(locate(code_words),locate(desc_words),locate(tariff_words))
        if all(v is not None for v in pos):
            found=(i,pos)
            break
    if not found:
        raise ValueError(f"{name}: se requieren encabezados de codigo, descripcion y tarifa")
    head_idx,(ci,di,ti)=found
    # Consumir todas las filas; no alterar los valores originales.
    from itertools import chain
    items=chain((r for r in sampled if r[0]>head_idx),it)
    data=[]
    for n,row in items:
        def cell(i):return str(row[i] if i<len(row) else "").strip()
        code,desc,tariff=cell(ci),cell(di),cell(ti)
        if not (code or desc or tariff):continue
        data.append({"row":n,"code":code,"desc":desc,"tariff":tariff,
                     "norm":normalize(desc),"money":amount(tariff)})
    if not data:raise ValueError(f"{name}: no contiene tecnologías")
    return data

def load_legacy():
    path=OUT/"resultado_homologacion.csv"
    if not path.exists():return {}
    with path.open(encoding="utf-8-sig",newline="") as f:
        records=list(csv.DictReader(f,delimiter=";"))
    by_code=defaultdict(list)
    for r in records:by_code[r.get("codigo_prestador","").strip()].append(r)
    return by_code

def same_tariff(a,b):
    return a["money"] is not None and b["money"] is not None and a["money"]==b["money"]

def score(a,b):
    return round(similarity(a["norm"],b["norm"]),1) if a["norm"] and b["norm"] else 0

def record(a=None,b=None,decision="",motivo="",action="",proposed=None,score_val=None):
    old=proposed or {}
    similarity_score=score_val if score_val is not None else score(a,b) if a and b else ""
    money_diff=(str(a["money"]-b["money"]) if a and b and a["money"] is not None and b["money"] is not None else "")
    return {
       "origen": "ANEXO" if a else "HAM",
       "fila_anexo": a["row"] if a else "",
       "codigo_anexo": a["code"] if a else "",
       "descripcion_anexo": a["desc"] if a else "",
       "tarifa_anexo": a["tariff"] if a else "",
       "fila_ham": b["row"] if b else "",
       "codigo_ham": b["code"] if b else "",
       "descripcion_ham": b["desc"] if b else "",
       "tarifa_ham": b["tariff"] if b else "",
       "similitud_descripcion":similarity_score,
       "diferencia_tarifa":money_diff,
       "categoria_propuesta":old.get("tipo_servicio",""),
       "codigo_maestro_propuesto":old.get("codigo_homologado",""),
       "estado_homologacion_maestro":old.get("estado_homologacion",""),
       "decision":decision,"motivo":motivo,"accion_ham":action,
       "requiere_validacion":"NO" if decision=="COINCIDENCIA EXACTA" else "SI",
    }

def classify(a,b,proposed):
    s=score(a,b); money_ok=same_tariff(a,b)
    code_ok=key(a["code"])==key(b["code"]) and bool(a["code"])
    desc_ok=a["norm"]==b["norm"] and bool(a["norm"])
    if code_ok and desc_ok and money_ok:
        return "COINCIDENCIA EXACTA","Código, descripción normalizada y tarifa coinciden","MANTENER",s
    reason=[]
    if not code_ok:reason.append("Códigos diferentes o código propio; validar identidad tecnológica")
    if not desc_ok:reason.append(f"Descripción diferente ({s}%)")
    if not money_ok:reason.append("Tarifa diferente o no interpretable; verificar contrato")
    if proposed and proposed.get("estado_homologacion")!="COINCIDENCIA PROPUESTA":
        reason.append("Homologación de maestro sin validación técnica")
    if code_ok:
        decision="REVISAR DIFERENCIAS"
        action="ACTUALIZAR SOLO TRAS VALIDACION"
    elif s>=80 and money_ok:
        decision="CODIGO PROPIO / EQUIVALENCIA POR VALIDAR"
        action="HOMOLOGAR SOLO TRAS VALIDACION"
    else:
        decision="REVISAR IDENTIDAD TECNOLOGICA"
        action="REVISION MANUAL"
    return decision,"; ".join(reason),action,s

def compare(annex,ham,legacy):
    by_ham_code=defaultdict(list)
    for j,b in enumerate(ham):
        if b["code"]:by_ham_code[key(b["code"])].append(j)
    assigned=set()
    result=[]
    duplicates=Counter((key(a["code"]),a["norm"]) for a in annex)
    price_variants=defaultdict(set)
    for a in annex:price_variants[(key(a["code"]),a["norm"])].add(a["tariff"])
    for a in annex:
        old_candidates=legacy.get(a["code"],[])
        proposal=next((x for x in old_candidates if x.get("descripcion_prestador","")==a["desc"]),old_candidates[0] if old_candidates else {})
        matching=[j for j in by_ham_code.get(key(a["code"]),[]) if j not in assigned]
        # Solo comparar por descripción+tarifa si el código no encuentra candidato único.
        match_type="codigo"
        if not matching:
            matching=[j for j,b in enumerate(ham) if j not in assigned and same_tariff(a,b) and score(a,b)>=80]
            match_type="descripcion_tarifa"
        # No escoger arbitrariamente entre dos filas válidas.
        scored=sorted(((score(a,ham[j]),j) for j in matching),reverse=True)
        if not scored:
            result.append(record(a,decision="EN ANEXO NO IDENTIFICADO EN HAM",motivo="Requiere cruce adicional por maestros; no se certifica ausencia contractual",action="EVALUAR CREACION",proposed=proposal))
            continue
        if len(scored)>1 and (scored[0][0]-scored[1][0]<5 or match_type=="codigo"):
            result.append(record(a,decision="MULTIPLES CANDIDATOS HAM",motivo=f"{len(scored)} registros posibles; evitar emparejamiento arbitrario",action="REVISION MANUAL",proposed=proposal))
            continue
        s,j=scored[0];b=ham[j]
        if match_type=="descripcion_tarifa" and (s<95 or len(scored)>1):
            result.append(record(a,b,decision="CODIGO PROPIO / EQUIVALENCIA POR VALIDAR",motivo="Código distinto y descripción aproximada: confirmar atributos clínicos",action="REVISION MANUAL",proposed=proposal,score_val=s))
            continue
        assigned.add(j)
        decision,motive,action,s=classify(a,b,proposal)
        if duplicates[(key(a["code"]),a["norm"])]>1 or len(price_variants[(key(a["code"]),a["norm"])])>1:
            decision="DUPLICIDAD CONTRACTUAL"
            action="REVISION MANUAL"
            motive+="; mismo código y descripción repetidos o con varias tarifas en anexo"
        result.append(record(a,b,decision=decision,motivo=motive,action=action,proposed=proposal,score_val=s))
    for j,b in enumerate(ham):
        if j not in assigned:
            result.append(record(b=b,decision="EN HAM SIN VINCULO CONFIRMADO EN ANEXO",
              motivo="Posible parametrización extra; verificar anexos, otrosíes, vigencias, sedes y contratos antes de inactivar",
              action="EVALUAR INACTIVACION"))
    return result

def write_report(rows,annex_count,ham_count):
    OUT.mkdir(exist_ok=True)
    with (OUT/"cruce_anexo_ham.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,delimiter=";");writer.writeheader();writer.writerows(rows)
    counts=Counter(r["decision"] for r in rows)
    report=["AUDITORÍA CONTRACTUAL ANEXO VS HAM",
      f"Filas anexo: {annex_count}",f"Filas HAM: {ham_count}",
      "El resultado NO autoriza altas, cambios ni inactivaciones automáticas.",
      "Una similitud >=80% genera candidato, NO equivalencia clínica.",
      "CUM, concentración, presentación, técnica y vigencia deben verificarse por fuente oficial.",
      "", "ESTADOS:",*(f"{k}: {v}" for k,v in sorted(counts.items()))]
    (OUT/"auditoria_anexo_ham.txt").write_text("\n".join(report)+"\n",encoding="utf-8")
    print("\n".join(report))

def main():
    OUT.mkdir(exist_ok=True)
    if not (ROOT/"HAM.xlsx").exists():
        text=("PENDIENTE: no se encontró HAM.xlsx en la raíz del repositorio.\n"
              "Se requiere exportación real de HAM con columnas codigo, descripcion, tarifa.\n"
              "No se ha realizado cruce contractual ni se recomiendan inactivaciones.\n")
        (OUT/"auditoria_anexo_ham.txt").write_text(text,encoding="utf-8")
        # Quitar datos contractuales antiguos para evitar decisiones basadas en un HAM anterior.
        (OUT/"cruce_anexo_ham.csv").write_text("estado;motivo\nPENDIENTE;HAM.xlsx no disponible\n",encoding="utf-8-sig")
        print(text)
        return
    annex=load_book("Prestador.xlsx")
    ham=load_book("HAM.xlsx")
    rows=compare(annex,ham,load_legacy())
    write_report(rows,len(annex),len(ham))

if __name__=="__main__":
    main()
