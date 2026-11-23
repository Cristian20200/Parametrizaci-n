# Parametrica — Auditoría contractual y homologación

## Fuentes

- `Prestador.xlsx`: **anexo tarifario contratado**. Debe contener `codigo_prestador`, `descripcion_prestador`, `valor_pactado`. Se admiten encabezados equivalentes `codigo`, `descripcion`, `tarifa`.
- `HAM.xlsx`: **exportación de tecnologías actualmente parametrizadas** desde HAM. Encabezados `codigo`, `descripcion`, `tarifa` (o equivalentes reconocidos por el lector).
- `CUPS.xlsx`, `subcodigos.xlsx`, `paquetes.xlsx`, `Medicamentos.xlsx`, `insumos.xlsx`: maestros de candidatos a homologación.
- `traza.xlsx`: trazabilidad histórica y referencias de tarifarios; **no certifica vigencia actual**.

Los códigos y subcódigos se deben guardar como **texto**: `997106-2` no equivale a `997106`.

## Flujo automático

1. Ejecutar `python scripts/homologar.py` para elaborar candidatos a homologación con maestros en `resultados/resultado_homologacion.csv`.
2. Ejecutar `python scripts/comparar_ham.py` para generar `resultados/cruce_anexo_ham.csv` y `resultados/auditoria_anexo_ham.txt`.
3. Revisar decisiones antes de aplicar cambios en HAM: **mantener, evaluar creación, revisar diferencias, revisar duplicidades, evaluar inactivación**. Ninguna operación se ejecuta automáticamente contra HAM.
4. Validar CUPS contra el catálogo oficial aplicable al periodo contractual. La comparación textual, la trazabilidad histórica y la presencia en un archivo maestro **no constituyen comprobación normativa**.

**Cuando todavía no existe `HAM.xlsx`**, se genera una auditoría marcada **PENDIENTE**. No se reportan supuestas ausencias o inactivaciones en HAM. Subir la exportación real antes de interpretar el cruce.

## Reglas de control

- La coincidencia contractual exacta implica igualdad de código, descripción normalizada y tarifa; la vigencia y equivalencia clínica se verifican por separado.
- Códigos propios pueden localizarse por descripción y tarifa. La coincidencia textual mínima del 80 % identifica candidatos, **no autoriza** homologación automática.
- Para un mismo código con descripciones o tarifas distintas, evaluar código base o subcódigo; no elegir variantes arbitrariamente.
- Para subcódigos usar siempre el identificador **completo** almacenado en la columna `subcodigo`. Si falta, registrar necesidad de crear o revisar; no reemplazarlo por `codigo_base`.
- Paquetes requieren validar alcance, CUPS incluidos, componentes y condiciones pactadas. La palabra «incluye» solo indica que deben revisarse.
- Medicamentos: comprobar principio activo, concentración, forma, presentación, CUM e información sanitaria aplicable; insumos/dispositivos: referencia, especificaciones, unidades y registro aplicable. Aun con coincidencia >80 %, diferencias críticas bloquean equivalencias.
- Una tecnología existente en HAM y ausente del anexo actual se marca como **candidata a evaluación de inactivación**, después de revisar otrosíes, anexos, vigencias, contratos y sedes.
- No alterar el valor pactado sin documentación contractual.

## Pruebas

```bash
python scripts/test_comparar_ham.py
```

La automatización de GitHub Actions debe ejecutarse ante cambios en `Prestador.xlsx`, `HAM.xlsx`, maestros, scripts o workflow.

## Controles incorporados para ejercicios posteriores (noviembre de 2026)

- El cruce `scripts/comparar_ham.py` utiliza código completo (incluido el sufijo), tarifa, texto clínico normalizado, concentración y forma farmacéutica para **proponer** candidatos. No aprueba equivalencias por tarifa igual.
- Se bloquean los emparejamientos basados únicamente en tarifa cuando se detectan principios activos/formulaciones diferentes (p. ej. losartán frente a losartán + hidroclorotiazida) o formas farmacéuticas distintas (p. ej. jalea frente a crema).
- Expresiones `8 MG/4 ML` y `2 MG/ML` permiten comparar concentraciones (2 mg/mL), pero se revisan por separado la dosis total, la vía, la presentación y el registro sanitario. La expresión `X 4 ML` indica presentación; por sí sola no prueba concentración.
- Las columnas `descripcion_maestro_propuesto` y `similitud_anexo_maestro` se mantienen en el CSV. La similitud es orientativa, **no una tasa de acierto clínico**.
- Para homologaciones con medicamentos, los controles actuales **no constituyen un validador completo** de todos los ingredientes, sales, concentración, forma, vía y CUM: cuando falte evidencia debe revisarse manualmente.
- La estadística refleja candidatos detectados; **sin un conjunto de verdad validado por profesionales no puede medirse precisión real**.
- Las pruebas de regresión incluyen diferencias de dosis, incompatibilidades farmacéuticas y subcódigos, y deben pasar antes de publicar resultados.

## Cruce inverso HAM → Anexo (revisión del archivo manual)

Desde la revisión del libro `cruce_anexo_ham(1).xlsx`, el motor también compara las filas de HAM no vinculadas contra el anexo por tarifa y descripción, verificando incompatibilidades detectables. El nuevo estado `HAM CANDIDATO ANEXO POR VERIFICAR` señala un **posible** vínculo contractual, sin darlo por equivalente ni autorizar inactivación. Los candidatos aparecen en `resultados/cruce_anexo_ham.csv` con ambas descripciones, tarifas, puntuación y justificación.

Las fórmulas de búsqueda/similitud del archivo manual no son datos certificados: por ejemplo, misma tarifa puede relacionar insulina con ácido fólico o presentaciones diferentes. Las decisiones se validan por atributos y documentos aplicables; no trasladar automáticamente los resultados de una fórmula a los maestros.

Pruebas de regresión añadidas: `METOTREXATE` / `METOTREXATO`, trimebutina 10 mg/mL frente a 50 mg/5 mL, presentación distinta de fenoterol/ipratropio, y rechazo de relación insulina/ácido fólico solo por tarifa.

## Bloqueo de seguridad de códigos no vigentes (23 de noviembre de 2026)

Se ha detectado que los maestros locales pueden contener códigos históricos o sin vigencia oficial comprobada. **Ningún código de maestro se debe copiar a HAM por el mero hecho de parecerse a un concepto del anexo.** En tanto no haya una fuente oficial del periodo contractual incorporada y validada por tipo de tecnología:

- `codigo_homologado` y, por propagación, `codigo_maestro_propuesto` se dejan **vacíos**; no son campos de carga automática.
- `codigo_candidato_no_validado` conserva el identificador exploratorio únicamente para investigación; `estado_vigencia_codigo` muestra `VIGENCIA OFICIAL NO VERIFICADA` y `fuente_vigencia_codigo` explica la ausencia de soporte. Esta regla es preventiva, **no indica que todos los códigos sean inválidos**.
- Los registros con `estado` interno marcado expresamente como inactivo/no vigente/derogado/vencido se excluyen de los candidatos; una etiqueta local `ACTIVO` o `VIGENTE` **no constituye certificación oficial**.
- Para CUPS exigir el catálogo/resolución oficial aplicable; para medicamentos verificar las fuentes sanitarias oficiales de CUM/INVIMA y la presentación precisa; para insumos, paquetes y subcódigos corroborar la vigencia de la parametrización local y el contrato. Un histórico `traza.xlsx` no constituye certificación normativa.
- Los códigos que figuran en `codigo_ham` representan lo ya exportado de HAM, **no una recomendación nueva** ni comprobación de vigencia.

Hasta que se incorpore una fuente de referencia verificada, Parametrica puede **sugerir descripciones para revisión**, pero no ofrecer códigos como candidatos de aplicación directa.
