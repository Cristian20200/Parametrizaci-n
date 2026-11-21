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
