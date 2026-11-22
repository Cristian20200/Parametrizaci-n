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
          "codigo_maestro_propuesto","descripcion_maestro_propuesto","similitud_anexo_maestro","estado_homologacion_maestro",
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


# Equivalencias de redacción (no equivalencias clínicas automáticas).
ALIASES = [
    (r"\bTAB\s*/\s*CAP\b", " TABLETA CAPSULA "),
    (r"\bTAB(?:LETA)?S?\b", " TABLETA "),
    (r"\bCAP(?:SULA)?S?\b", " CAPSULA "),
    (r"\bINY(?:ECTABLE|ECCION|ECCION(?:ES)?)?\.?\b", " INYECTABLE "),
    (r"\bSLN\b|\bSOL\b|\bSOLUCION\b", " SOLUCION "),
    (r"\bAMP\b|\bAMPOLLA\b", " AMPOLLA "),
    (r"\bFCO\b|\bFRASCO\b", " FRASCO "),
    (r"\bTUB\b|\bTUBO\b", " TUBO "),
    (r"\bRX\b|\bRADIOGRAFIA\b", " RADIOGRAFIA "),
    (r"\bTRANSFUSION\b|\bTRANSFUSIONES\b", " TRANSFUSION "),
    (r"\bINYECCIONES?\b", " INYECTABLE "),
    (r"\bMG\b", " MG "),
    (r"\bML\b", " ML "),
    (r"\bPROFILAXIS\b", " PROFILAXIS "),
]
def clinical_text(s):
    s=unicodedata.normalize("NFKD",str(s or "").upper())
    s="".join(ch for ch in s if not unicodedata.combining(ch))
    s=s.replace("µG","MCG").replace("μG","MCG")
    for pattern,replacement in ALIASES:
        s=re.sub(pattern,replacement,s)
    # Mantener juntos números, unidades y símbolos: 10MG/1ML es una concentración.
    s=re.sub(r"(?<=\d)\s+(?=MG\b|ML\b|G\b|MCG\b|UI\b)", "", s)
    s=re.sub(r"(?<=MG|ML)\s*/\s*(?=\d)", "/",s) if False else s
    s=re.sub(r"(\d+(?:[.,]\d+)?)\s*(MG|MCG|G|UI)\s*/\s*(\d+(?:[.,]\d+)?)\s*(ML|L)\b",r"\1\2/\3\4",s)
    s=re.sub(r"[^A-Z0-9/.,]+"," ",s)
    return " ".join(s.split())
def clinical_tokens(s):
    # Evitar que una abreviatura comun penalice el emparejamiento.
    return set(re.findall(r"[A-Z]+|\d+(?:[.,]\d+)?(?:MG|MCG|ML|UI|G|L)?", clinical_text(s)))
def concentration(s):
    """Concentraciones normalizadas a mg/ml (o UI/ml), sin inferir equivalencia por marca."""
    text=clinical_text(s)
    matches=re.findall(r"\b(\d+(?:[.,]\d+)?)\s*(MCG|MG|G|UI)\s*/\s*(\d+(?:[.,]\d+)?)\s*(ML|L)\b",text)
    values=set()
    for mass,unit,volume,vunit in matches:
        m=Decimal(mass.replace(",","."));v=Decimal(volume.replace(",","."))
        if not v:continue
        if unit=="MCG":m=m/Decimal(1000);unit="MG"
        if unit=="G":m=m*Decimal(1000);unit="MG"
        if vunit=="L":v=v*Decimal(1000)
        values.add((unit,m/v))
    return values
def numeric_specs(s):
    s=clinical_text(s)
    # Toda cifra con unidad se mantiene como atributo técnico.
    return set(re.findall(r"\b\d+(?:[.,]\d+)?(?:MG|MCG|G|ML|L|UI)\b",s))
def clinical_conflict(a,b):
    ca,cb=concentration(a["desc"]),concentration(b["desc"])
    if ca and cb:
        if ca!=cb:return "CONCENTRACION DIFERENTE"
        # Una misma concentración no garantiza la misma presentación, pero
        # evita interpretar 8mg/4ml y 2mg/ml como sustancias distintas.
        return ""
    na,nb=numeric_specs(a["desc"]),numeric_specs(b["desc"])
    if na and nb and na!=nb:
        return "CANTIDAD O UNIDAD DIFERENTE"
    return ""
def clinical_score(a,b):
    atext,btext=clinical_text(a["desc"]),clinical_text(b["desc"])
    if not atext or not btext:return 0.
    ta,tb=clinical_tokens(a["desc"]),clinical_tokens(b["desc"])
    overlap=100*len(ta&tb)/len(ta|tb) if ta and tb else 0
    # El nombre corto sigue siendo informativo aunque el otro incluya presentación.
    coverage=100*len(ta&tb)/min(len(ta),len(tb)) if ta and tb else 0
    result=.50*similarity(atext,btext)+.30*overlap+.20*coverage
    ca,cb=concentration(a["desc"]),concentration(b["desc"])
    if ca and cb and ca==cb:result=max(result,75)
    return round(result,1)

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
       "descripcion_maestro_propuesto":old.get("descripcion_homologada",""),
       "similitud_anexo_maestro":round(similarity(clinical_text(a["desc"]),clinical_text(old.get("descripcion_homologada",""))),1) if a and old.get("descripcion_homologada") else "",
       "estado_homologacion_maestro":old.get("estado_homologacion",""),
       "decision":decision,"motivo":motivo,"accion_ham":action,
       "requiere_validacion":"SI - VIGENCIA Y ATRIBUTOS TECNICOS" if decision=="COINCIDENCIA EXACTA" else "SI",
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
    """Cruce bidireccional uno a uno; sin deducir bajas definitivas."""
    by_code=defaultdict(list)
    by_tariff=defaultdict(list)
    for j,b in enumerate(ham):
        by_code[key(b["code"])].append(j)
        if b["money"] is not None:by_tariff[b["money"]].append(j)

    # Priorizar acuerdos claros globalmente, no procesar filas en orden arbitrario.
    proposals=[]
    ambiguity=defaultdict(list)
    duplicates=Counter((key(a["code"]),clinical_text(a["desc"]),a["money"]) for a in annex)
    code_desc=defaultdict(set)
    code_prices=defaultdict(set)
    for a in annex:
        code_desc[key(a["code"])].add(clinical_text(a["desc"]))
        code_prices[key(a["code"])].add(a["money"])
    for i,a in enumerate(annex):
        old=legacy.get(a["code"],[])
        master=next((x for x in old if x.get("descripcion_prestador","")==a["desc"]),old[0] if old else {})
        candidate_ids=set(by_code.get(key(a["code"]),[]))
        if a["money"] is not None:
            candidate_ids.update(by_tariff[a["money"]])
        # Reintentar con el codigo del maestro propuesto, sin perder el sufijo.
        mk=key(master.get("codigo_homologado",""))
        if mk:
            candidate_ids.update(by_code.get(mk,[]))
        for j in candidate_ids:
            b=ham[j]
            exact_code=bool(a["code"]) and key(a["code"])==key(b["code"])
            master_code=bool(mk) and mk==key(b["code"])
            tariff_ok=same_tariff(a,b)
            s=clinical_score(a,b)
            same_desc=clinical_text(a["desc"])==clinical_text(b["desc"])
            if not exact_code and not master_code and not tariff_ok:
                continue
            if not exact_code and not master_code and s<65:
                continue
            conflict=clinical_conflict(a,b)
            # Las diferencias de concentración no desaparecen por tarifa/código iguales.
            if exact_code and same_desc and tariff_ok and not conflict:
                tier=7
            elif exact_code and tariff_ok and s>=70 and not conflict:
                tier=6
            elif master_code and tariff_ok and s>=72 and not conflict:
                tier=5
            elif tariff_ok and s>=88 and not conflict:
                tier=4
            elif tariff_ok and s>=70 and not conflict:
                tier=3
            elif exact_code and s>=60:
                tier=2
            elif master_code and s>=60:
                tier=1
            else:
                continue
            proposals.append((tier,s,i,j,conflict,master))
            ambiguity[i].append((tier,s,j))
    proposals.sort(key=lambda x:(x[0],x[1]),reverse=True)
    # No asignar automaticamente un par si hay empate de calidad contra varios HAM.
    uncertain=set()
    for i,options in ambiguity.items():
        options.sort(reverse=True)
        if len(options)>=2 and options[0][0]==options[1][0] and options[0][1]-options[1][1]<2:
            uncertain.add(i)
    chosen={}
    assigned=set()
    for tier,s,i,j,conflict,master in proposals:
        if i in chosen or j in assigned or i in uncertain:continue
        chosen[i]=(j,tier,s,conflict,master)
        assigned.add(j)
    result=[]
    for i,a in enumerate(annex):
        old=legacy.get(a["code"],[])
        master=next((x for x in old if x.get("descripcion_prestador","")==a["desc"]),old[0] if old else {})
        if i in uncertain:
            result.append(record(a,decision="MULTIPLES CANDIDATOS HAM",
               motivo="Dos o mas candidatos con puntuacion equivalente; no decidir por orden de filas",
               action="REVISION MANUAL",proposed=master))
            continue
        if i not in chosen:
            result.append(record(a,decision="EN ANEXO SIN VINCULO CONFIRMADO",
               motivo="Sin emparejamiento seguro; validar maestro, codigo propio, descripcion y tarifa antes de crear",
               action="EVALUAR CREACION",proposed=master))
            continue
        j,tier,s,conflict,master=chosen[i]
        b=ham[j]
        code_ok=key(a["code"])==key(b["code"])
        tariff_ok=same_tariff(a,b)
        same_desc=clinical_text(a["desc"])==clinical_text(b["desc"])
        if conflict:
            decision="CONFLICTO TECNICO"
            motive=f"{conflict}; cotejar concentracion, unidad, presentacion o tecnica"
            action="REVISION TECNICA"
        elif code_ok and tariff_ok and same_desc:
            decision="COINCIDENCIA EXACTA"
            motive="Mismo codigo, descripcion normalizada y tarifa"
            action="MANTENER"
        elif tariff_ok and code_ok:
            decision="COINCIDENCIA DESCRIPTIVA PROBABLE"
            motive=f"Mismo codigo y tarifa; descripcion equivalente parcialmente ({s}%). Confirmar tecnica"
            action="VALIDAR DESCRIPCION"
        elif tariff_ok:
            decision="EQUIVALENCIA PROPUESTA POR DESCRIPCION Y TARIFA"
            motive=f"Codigos distintos o propios; tarifa igual y similitud tecnica {s}%; corroborar identidad"
            action="VALIDAR CODIGO Y DESCRIPCION"
        else:
            decision="DIFERENCIA TARIFARIA O DESCRIPTIVA"
            motive=f"Codigo relacionado, tarifa diferente; similitud {s}%; verificar valor pactado"
            action="REVISAR TARIFA"
        if len(code_desc[key(a["code"])])>1:
            decision="MISMO CODIGO CON VARIANTES"
            motive+="; varias descripciones del mismo codigo en anexo: validar base y subcodigo existente"
            action="REVISAR SUBCODIGO"
        if duplicates[(key(a["code"]),clinical_text(a["desc"]),a["money"])]>1:
            decision="DUPLICADO CONTRACTUAL"
            motive+="; misma tecnologia duplicada en anexo"
            action="REVISAR DUPLICADO"
        if len(code_prices[key(a["code"])])>1:
            motive+="; codigo con varias tarifas: verificar convenio y unidad de cobro"
        if re.search(r"\b(PAQUETE|INCLUYE)\b",clinical_text(a["desc"])):
            motive+="; verificar alcance de paquete y componentes, no inferirlo solo por palabra incluye"
        if master.get("tipo_servicio") in ("MEDICAMENTO","INSUMO"):
            motive+="; validar principio activo/concentracion/presentacion o referencia y registro sanitario"
            if decision in ("COINCIDENCIA EXACTA","COINCIDENCIA DESCRIPTIVA PROBABLE"):
                decision="VALIDACION TECNICA MEDICAMENTO O INSUMO"
                action="REVISION TECNICA"
        result.append(record(a,b,decision=decision,motivo=motive,action=action,proposed=master,score_val=s))
    for j,b in enumerate(ham):
        if j not in assigned:
            result.append(record(b=b,decision="EN HAM SIN VINCULO CONFIRMADO EN ANEXO",
              motivo="Posible registro no contratado o candidato ambiguo; verificar otrosies, anexos, sedes y periodo contractual",
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
