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

def read_xlsx(path, sheet_index=0):
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
        with z.open(sheet_names[sheet_index]) as f:
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

def master_validity(extra):
    """El estado interno del maestro no acredita vigencia normativa actual."""
    raw=" ".join(str(v or "") for k,v in extra.items()
                 if "ESTADO" in k or "VIGENCIA" in k)
    status=plain(raw)
    if re.search(r"\b(NO VIGENTE|INACTIVO|INACTIVA|DEROGADO|DEROGADA|ANULADO|ANULADA|VENCIDO|VENCIDA|CANCELADO|CANCELADA|SUSPENDIDO|SUSPENDIDA|RETIRADO|RETIRADA|OBSOLETO|OBSOLETA)\b",status):
        return "NO VIGENTE SEGUN MAESTRO"
    return "VIGENCIA OFICIAL NO VERIFICADA"

def main():
    os.makedirs(ROOT/'resultados',exist_ok=True)
    records=[]; index=collections.defaultdict(set); file_counts={}
    header_report=['ORDEN DE BUSQUEDA: CUPS > SUBCODIGO > PAQUETE > MEDICAMENTO > INSUMO']
    for fname in FILES:
        hs,rows,cols=get_table(fname)
        file_counts[fname]=0
        # Para SUBCODIGO, usar la clave completa y NO codigo_base.
        sub_idx=base_idx=None
        if fname=='subcodigos.xlsx':
            normalized_headers=[normalize(h).replace(' ','_') for h in hs]
            base_aliases=('CODIGO_BASE','CODIGO_BASE_CUPS')
            sub_aliases=('SUBCODIGO','CODIGO_RELACIONADO_AL_SUBCODIGO','CODIGO_RELACIONADO_AL_SUB_CODIGO')
            base_idx=next((i for i,h in enumerate(normalized_headers) if h in base_aliases),None)
            sub_idx=next((i for i,h in enumerate(normalized_headers) if h in sub_aliases),None)
            if base_idx is None or sub_idx is None or base_idx==sub_idx:
                raise ValueError(f'subcodigos.xlsx: no se localizaron ambas columnas codigo_base y subcodigo: {hs!r}')
        for row in rows:
            code=val(row,cols[0]);desc=val(row,cols[1])
            if fname=='subcodigos.xlsx':
                base=val(row,base_idx).strip()
                suffix=val(row,sub_idx).strip()
                if not suffix:
                    raise ValueError(f'Subcodigo vacio para codigo_base={base!r}, descripcion={desc!r}')
                # Algunas fuentes contienen solo el sufijo: reconstruir codigo_base-sufijo.
                if re.fullmatch(r'\d+(?:\.0)?',suffix) and base and suffix!=base:
                    suffix=suffix.removesuffix('.0')
                    code=f'{base}-{suffix}'
                else:
                    code=suffix
                if code==base:
                    raise ValueError(f'Subcodigo indistinguible del codigo_base={base!r}; revisar maestro')
            if not code or not desc:continue
            rec={'type':TYPES[fname],'file':fname,'code':code,'description':desc,'norm':normalize(desc),'tokens':tokenize(desc),'extra':{}}
            for i,h in enumerate(hs):
                nh=normalize(h)
                if any(k in nh for k in ['EXPEDIENTE','REGISTRO SANITARIO','REGISTRO_SANITARIO','VIGENCIA','ESTADO','TITULAR']):
                    rec['extra'][nh]=val(row,i)
            rec['validity']=master_validity(rec['extra'])
            if rec['validity']=='NO VIGENTE SEGUN MAESTRO':
                file_counts[fname+'_no_vigentes_excluidos']=file_counts.get(fname+'_no_vigentes_excluidos',0)+1
                continue
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
        more=' | '.join(f"NO VALIDADO {records[j]['type']}:{records[j]['code']} ({round(s,1)}%)" for s,j in top[1:3])
        ex=best['extra'] if best else {}
        exp=next((v for k,v in ex.items() if 'EXPEDIENTE' in k),'')
        reg=next((v for k,v in ex.items() if 'REGISTRO' in k),'')
        # BLOQUEO: sin padrón oficial vigente validado para el período del contrato,
        # no publicar un código como maestro propuesto utilizable. El candidato
        # queda solo como evidencia explícitamente NO VALIDADA.
        candidate_code=best['code'] if best else ''
        if best:
            obs.append('BLOQUEADO: vigencia oficial no comprobada; no utilizar código candidato en parametrización')
            status='CANDIDATO NO VALIDADO - VIGENCIA PENDIENTE'
        rows_out.append([codigo,desc,precio,best['type'] if best else '',
                         '',best['description'] if best else '',score if best else '',
                         exp,reg,status,'; '.join(obs),more,best['file'] if best else '',
                         candidate_code,
                         'VIGENCIA OFICIAL NO VERIFICADA' if best else 'SIN CANDIDATO',
                         'SIN FUENTE OFICIAL VIGENTE APORTADA'])
        totals[status]+=1
        if n%500==0:print('Procesados',n,flush=True)
    # La traza es evidencia histórica; no se usa como nomenclador ni para certificar vigencia.
    traza_file=ROOT/'traza.xlsx'
    traza_info=['TRAZA: archivo no disponible']
    traza_lookup=collections.Counter()
    if traza_file.exists():
        # Buscar la tabla principal entre TODAS las hojas: la primera suele ser introductoria.
        from itertools import chain, islice
        with zipfile.ZipFile(traza_file) as z:
            sheets=[n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+.xml',n)]
        best=(-1,0,0,[])
        def score_header(row):
            fields=[normalize(v) for v in row if 0<len(str(v).strip())<=90]
            has_code=any('CODIGO' in h or h in ('CUPS','COD CUPS') for h in fields)
            if not has_code:return 0
            return sum(3 for h in fields if 'CODIGO' in h or h in ('CUPS','COD CUPS')) + sum(1 for h in fields if any(s in h for s in ('DESCRIPCION','TARIFA','PROCEDIMIENTO','VALOR','VIGENCIA','ESTADO')))
        for sheet_i in range(len(sheets)):
            preview=list(islice(read_xlsx(traza_file,sheet_i),200))
            for pos,row in enumerate(preview):
                score=score_header(row)
                if score>best[0]:best=(score,sheet_i,pos,row)
        header_score,sheet_idx,header_pos,traza_header=best
        traza_names=[normalize(h) for h in traza_header]
        traza_code_cols=[i for i,h in enumerate(traza_names) if len(h)<=90 and (('CODIGO' in h) or h in ('CUPS','COD CUPS'))]
        traza_rows=islice(read_xlsx(traza_file,sheet_idx),header_pos+1,None)
        traza_count=0
        for tr in traza_rows:
            traza_count+=1
            for i in traza_code_cols:
                code=val(tr,i).upper().replace(' ','')
                if code and len(code)<=60:
                    traza_lookup[code]+=1
        traza_info=[
            f'TRAZA: hojas={len(sheets)}, hoja_seleccionada={sheet_idx+1}, puntuacion_encabezado={header_score}, filas_datos={traza_count}, encabezado_fila={header_pos+1}, encabezados={traza_header[:30]}',
            f'TRAZA: columnas de códigos detectadas={[(i,traza_header[i]) for i in traza_code_cols]}',
            'TRAZA: coincidencias de códigos son antecedentes, NO equivalencia clínica ni vigencia oficial'
        ]
    traza_original=0
    traza_candidato=0
    for record in rows_out:
        original=record[0].upper().replace(' ','')
        candidato=record[13].upper().replace(' ','')
        cnt_o=traza_lookup.get(original,0)
        cnt_c=traza_lookup.get(candidato,0) if candidato else 0
        traza_original+=bool(cnt_o)
        traza_candidato+=bool(cnt_c)
        record.extend([cnt_o,cnt_c,'ANTECEDENTE / NO VALIDADO' if cnt_o or cnt_c else 'SIN ANTECEDENTE POR CODIGO'])
    traza_info.extend([f'Filas de prestador con código en traza: {traza_original}',f'Filas de prestador cuyo candidato aparece en traza: {traza_candidato}'])
    output=ROOT/'resultados'/'resultado_homologacion.csv'
    columns=['codigo_prestador','descripcion_prestador','valor_pactado','tipo_servicio','codigo_homologado','descripcion_homologada','porcentaje_coincidencia','expediente_invima','registro_sanitario','estado_homologacion','observacion','otras_coincidencias','maestro_origen','codigo_candidato_no_validado','estado_vigencia_codigo','fuente_vigencia_codigo','apariciones_codigo_prestador_traza','apariciones_codigo_homologado_traza','estado_traza']
    with open(output,'w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f,delimiter=';');writer.writerow(columns);writer.writerows(rows_out)
    report=['AUDITORÍA DE HOMOLOGACIÓN DE PRESTADOR',f'Filas procesadas: {len(rows_out)}','',
            'MAESTROS:',*header_report,'','TRAZABILIDAD:',*traza_info,'','ESTADOS:',*(f'{k}: {v}' for k,v in sorted(totals.items())),'',
            'IMPORTANTE: Un parecido >=80% no equivale a homologación clínica ni valida expedientes INVIMA.',
            'Códigos y valores originales preservados. Revisar concentración, técnica y vigencia oficial.',
            'BLOQUEO DE SEGURIDAD: codigo_homologado vacio mientras no exista acreditacion de vigencia oficial para el periodo contractual.',
            'Los codigos exploratorios estan SOLO en codigo_candidato_no_validado; no deben cargarse a HAM.',
            'Las etiquetas ACTIVO/VIGENTE de maestros locales no acreditan por si solas la vigencia normativa o sanitaria.',
            'Fuente: maestros contenidos en el mismo repositorio y rama utilizada.']
    (ROOT/'resultados'/'auditoria_homologacion.txt').write_text('\n'.join(report),encoding='utf-8')
    print('\n'.join(report))
if __name__=='__main__':
    main()
