#!/usr/bin/env python3
"""Homologación conservadora de Prestador.xlsx contra cinco maestros.
Genera CSV (Excel UTF-8) y reporte de auditoría sin inventar expedientes."""
import csv, re, os, zipfile, unicodedata, collections, difflib
from xml.etree import ElementTree as ET
from pathlib import Path
try:
    from rapidfuzz import fuzz
    similarity=lambda a,b: fuzz.token_sort_ratio(a,b)
except ImportError:
    similarity=lambda a,b: difflib.SequenceMatcher(None,a,b).ratio()*100

ROOT=Path(__file__).resolve().parents[1]
NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
STOP={'DE','DEL','LA','EL','EN','CON','SIN','PARA','POR','X','Y','O','UN','UNA','UND','AMP','TAB','TABLETA','SOLUCION','INYECTABLE','FRASCO','FCO','SOD','MG','ML','G','NO','NUMERO'}
HEADERS={
'Prestador.xlsx':[['codigo_prestador','codigo','codigo modo test','codigo prestador'],['descripcion_prestador','descripcion','descripcion prestador'],['valor_pactado','valor','tarifa','precio']],
'CUPS.xlsx':[['codigo_cups','codigo','cups'],['descripcion_cups','descripcion','nombre']],
'Medicamentos.xlsx':[['codigo_medicamento','codigo','cum','codigo modo'],['descripcion_medicamento','descripcion','nombre']],
'insumos.xlsx':[['codigo_insumo','codigo'],['descripcion_insumo','descripcion','nombre']],
'paquetes.xlsx':[['codigo_paquete','codigo'],['descripcion_paquete','descripcion','nombre']],
'subcodigos.xlsx':[['subcodigo','codigo_base','codigo'],['descripcion_subcodigo','descripcion','nombre']],
}
FILES=['CUPS.xlsx','subcodigos.xlsx','paquetes.xlsx','Medicamentos.xlsx','insumos.xlsx']
TYPES={'CUPS.xlsx':'CUPS','Medicamentos.xlsx':'MEDICAMENTO','insumos.xlsx':'INSUMO','paquetes.xlsx':'PAQUETE','subcodigos.xlsx':'SUBCODIGO'}

def plain(s):
    s=unicodedata.normalize('NFKD',str(s or ''))
    return ''.join(c for c in s if not unicodedata.combining(c)).upper().strip()
def normalize(s):
    s=plain(s).replace(',','.')
    s=re.sub(r'\b(CAPSULAS?|TABLETAS?|COMPRIMIDOS?)\b','TABLETA',s)
    s=re.sub(r'\b(AMPOLLAS?|VIALES?)\b','AMPOLLA',s)
    s=re.sub(r'[^A-Z0-9.]+',' ',s)
    return ' '.join(s.split())
def tokenize(s):
    return [t for t in normalize(s).split() if t not in STOP and len(t)>=3]
def col_idx(ref):
    letters=re.match(r'[A-Z]+',ref)
    n=0
    for c in letters.group():n=n*26+ord(c)-64
    return n-1

def read_xlsx(path):
    # Lector de solo lectura usando el formato XML abierto XLSX (sin alterar maestros).
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        shared=[]
        if 'xl/sharedStrings.xml' in names:
            with z.open('xl/sharedStrings.xml') as f:
                for _,elem in ET.iterparse(f,events=('end',)):
                    if elem.tag==NS+'si':
                        shared.append(''.join(x.text or '' for x in elem.iter(NS+'t')))
                        elem.clear()
        sheet_names=sorted([n for n in names if re.fullmatch(r'xl/worksheets/sheet\d+.xml',n)],key=lambda p:int(re.search(r'sheet(\d+)',p).group(1)))
        if not sheet_names:raise ValueError('Sin hojas XML')
        with z.open(sheet_names[0]) as f:
            for _,elem in ET.iterparse(f,events=('end',)):
                if elem.tag==NS+'row':
                    cells={}
                    for cell in elem.findall(NS+'c'):
                        ref=cell.get('r','A1')
                        v=cell.find(NS+'v')
                        t=cell.get('t')
                        if t=='inlineStr':
                            st=''.join(i.text or '' for i in cell.iter(NS+'t'))
                        else:
                            st=v.text if v is not None else ''
                            if t=='s' and st:
                                try:st=shared[int(st)]
                                except (IndexError,ValueError):pass
                        cells[col_idx(ref)]=st
                    if cells:
                        yield [cells.get(i,'') for i in range(max(cells)+1)]
                    elem.clear()

def get_table(filename):
    rows=read_xlsx(ROOT/filename)
    first=[next(rows,[]) for _ in range(5)]
    opts=HEADERS[filename]
    candidates=[]
    for idx,row in enumerate(first):
        normal=[normalize(x).replace(' ','_') for x in row]
        matches=[]
        for variants in opts:
            valid={normalize(v).replace(' ','_') for v in variants}
            match=next((i for i,v in enumerate(normal) if v in valid),None)
            matches.append(match)
        candidates.append((sum(v is not None for v in matches),idx,matches))
    score,header_i,matches=max(candidates,key=lambda x:x[0])
    if score<2:raise ValueError(f'{filename}: Encabezados desconocidos. Primeras filas: {first[:3]}')
    headers=first[header_i]
    from itertools import chain
    allrows=chain(first[header_i+1:],rows)
    return headers, (row for row in allrows if any(str(v).strip() for v in row)),matches

def val(row,i):
    return str(row[i] if i is not None and i<len(row) else '').strip()

def main():
    os.makedirs(ROOT/'resultados',exist_ok=True)
    records=[]; index=collections.defaultdict(set); file_counts={}
    header_report=['ORDEN DE BUSQUEDA: CUPS > SUBCODIGO > PAQUETE > MEDICAMENTO > INSUMO']
    for fname in FILES:
        hs,rows,cols=get_table(fname)
        file_counts[fname]=0
        for row in rows:
            code=val(row,cols[0]);desc=val(row,cols[1])
            if not code or not desc:continue
            rec={'type':TYPES[fname],'file':fname,'code':code,'description':desc,'norm':normalize(desc),'tokens':tokenize(desc),'extra':{}}
            for i,h in enumerate(hs):
                nh=normalize(h)
                if any(k in nh for k in ['EXPEDIENTE','REGISTRO SANITARIO','REGISTRO_SANITARIO','VIGENCIA','ESTADO','TITULAR']):
                    rec['extra'][nh]=val(row,i)
            pos=len(records);records.append(rec)
            for tok in set(rec['tokens']):
                index[tok].add(pos)
            file_counts[fname]+=1
        header_report.append(f'{fname}: campos={hs}, columnas_codigo_descripcion={cols[:2]}, registros={file_counts[fname]}')
    _,prestador,pc=get_table('Prestador.xlsx')
    rows_out=[]; totals=collections.Counter()
    for n,row in enumerate(prestador,1):
        codigo=val(row,pc[0]);desc=val(row,pc[1]);precio=val(row,pc[2]) if len(pc)>2 else ''
        if not codigo and not desc:continue
        norm=normalize(desc)
        tokens=tokenize(desc)
        unique=sorted(set(tokens),key=lambda t:len(index.get(t,())))
        candidates=set()
        for token in unique[:7]:
            s=index.get(token,set())
            if 0<len(s)<25000:candidates.update(s)
            if len(candidates)>4500:break
        if not candidates: candidates=set(range(min(len(records),15000)))
        ranked=[]
        for j in candidates:
            m=records[j]
            if not m['norm']:continue
            score=similarity(norm,m['norm'])
            # Evita emparejamientos débiles por listas comunes; asignación siempre supervisada.
            if score>=70:ranked.append((score,j))
        # Orden estricto de los maestros definido por el usuario.
        # Un maestro se considera válido SOLO si existe coincidencia >=80%
        # Y no hay incompatibilidad detectada de concentración, vía o ingrediente.
        # Coincidencias dudosas no bloquean los maestros posteriores.
        order=['CUPS','SUBCODIGO','PAQUETE','MEDICAMENTO','INSUMO']
        ranked.sort(key=lambda pair:-pair[0])
        route_terms=['INYECTABLE','AMPOLLA','TABLETA','JARABE','SUSPENSION','CREMA','GOTAS','CAPSULA','INHALADOR','OVULO']
        def evaluate(pair):
            v,j=pair
            m=records[j]
            md=m['norm']
            digits1=set(re.findall(r'(?<!\\d)\\d+(?:\\.\\d+)?',norm))
            digits2=set(re.findall(r'(?<!\\d)\\d+(?:\\.\\d+)?',md))
            numeric=bool(digits1 and digits2 and digits1!=digits2)
            a={t for t in route_terms if t in norm}
            b={t for t in route_terms if t in md}
            route=bool(a and b and not a.intersection(b))
            important=[t for t in tokens[:3] if t not in {'ACIDO','SULFATO','CLORHIDRATO','SODICO'}]
            ingredient=bool(important and not set(important).intersection(m['tokens']))
            ambiguous=bool(m['type']=='MEDICAMENTO' and ('TAB CAP' in md or 'CAP TAB' in md))
            return numeric,route,ingredient,ambiguous
        eligible=[pair for pair in ranked if pair[0]>=80 and not any(evaluate(pair))]
        selected=None
        for category in order:
            choices=[pair for pair in eligible if records[pair[1]]['type']==category]
            if choices:
                selected=max(choices,key=lambda pair:pair[0])
                break
        # Si no hay coincidencia clínicamente aceptable, dar el mejor candidato
        # para revisión, sin declararlo homologado.
        if selected is None:
            for category in order:
                choices=[pair for pair in ranked if pair[0]>=80 and records[pair[1]]['type']==category]
                if choices:
                    selected=max(choices,key=lambda pair:pair[0])
                    break
        best=records[selected[1]] if selected else None
        score=round(selected[0],1) if selected else 0
        numeric_difference,route_difference,invalid_ingredient,ambiguous_form=(
            evaluate(selected) if selected else (False,False,False,False))
        top=[selected]+[pair for pair in ranked if pair!=selected][:4] if selected else ranked[:5]
        if not selected:status='SIN COINCIDENCIA >=80%'
        elif any((numeric_difference,route_difference,invalid_ingredient,ambiguous_form)):
            status='REVISIÓN TÉCNICA'
        else:status='COINCIDENCIA PROPUESTA'
        if not best or score<80:best=None
        obs=[]
        if numeric_difference:obs.append('Revisar concentración, medidas y presentación')
        if route_difference:obs.append('Revisar forma farmacéutica/vía')
        if invalid_ingredient:obs.append('Principio activo o sustancia por verificar')
        if ambiguous_form:obs.append('El maestro indica TAB/CAP: verificar forma farmacéutica exacta')
        if best and best['type']=='MEDICAMENTO':obs.append('Verificar expediente/registro según titular y producto')
        if best and best['type']=='SUBCODIGO':obs.append('Confirmar código base y metodología')
        if not best:obs.append('Sin maestro con similitud suficiente; revisar manualmente')
        more=' | '.join(f"{records[j]['type']}:{records[j]['code']} ({round(s,1)}%)" for s,j in top[1:3])
        ex=best['extra'] if best else {}
        exp=next((v for k,v in ex.items() if 'EXPEDIENTE' in k),'')
        reg=next((v for k,v in ex.items() if 'REGISTRO' in k),'')
        rows_out.append([codigo,desc,precio,best['type'] if best else '',best['code'] if best else '',best['description'] if best else '',score if best else '',exp,reg,status,'; '.join(obs),more,best['file'] if best else ''])
        totals[status]+=1
        if n%500==0:print('Procesados',n,flush=True)
    output=ROOT/'resultados'/'resultado_homologacion.csv'
    columns=['codigo_prestador','descripcion_prestador','valor_pactado','tipo_servicio','codigo_homologado','descripcion_homologada','porcentaje_coincidencia','expediente_invima','registro_sanitario','estado_homologacion','observacion','otras_coincidencias','maestro_origen']
    with open(output,'w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f,delimiter=';');writer.writerow(columns);writer.writerows(rows_out)
    report=['AUDITORÍA DE HOMOLOGACIÓN DE PRESTADOR',f'Filas procesadas: {len(rows_out)}','',
            'MAESTROS:',*header_report,'','ESTADOS:',*(f'{k}: {v}' for k,v in sorted(totals.items())),'',
            'IMPORTANTE: Un parecido >=80% no equivale a homologación clínica ni valida expedientes INVIMA.',
            'Códigos y valores originales preservados. Revisar concentración, técnica y vigencia oficial.',
            'Fuente: maestros contenidos en el mismo repositorio y rama utilizada.']
    (ROOT/'resultados'/'auditoria_homologacion.txt').write_text('\n'.join(report),encoding='utf-8')
    print('\n'.join(report))
if __name__=='__main__':
    main()
