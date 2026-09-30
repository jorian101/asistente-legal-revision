# Cómo modificar una plantilla

Estas plantillas (`.md`) son prompts, no plantillas Jinja: `PlantillaMarkdownAdapter`
(`backend/src/adapters/plantillas/plantilla_markdown_adapter.py`) las lee y hace
`str.replace()` de `{{VARIABLE}}` y `{{CONDICIONAL_*: ...}}`, sin lógica de
control. El resultado es el prompt que recibe el LLM — el LLM es quien
redacta el documento final siguiendo las instrucciones en cursiva
(`_(Regla de lógica para el Agente: ...)_`).

El criterio de formato (encabezado, considerandos, regla "Que,", cierre,
firmas) sale de documentos reales del vocal, documentados en el vault
(`asistente-legal-vault/wiki/estilo-documental/`, `wiki/criterio-vocal/`).
**No rediseñes el formato por tu cuenta** — si algo no coincide con el
vault, el vault manda; consultalo antes de cambiar la estructura.

## Agregar una sección

Escribí el encabezado Markdown (`### CONSIDERANDO...`, `#### 3.x. ...`) y el
texto en prosa debajo. Si necesitás que el LLM adapte el contenido al caso
concreto (no un dato fijo), agregá una instrucción en cursiva antes o
inmediatamente después del encabezado — mirá cómo lo hacen las secciones
existentes (p. ej. la nota condicional del Art. 29 Bis en
`proyecto_auto_vista_apelacion.md`).

## Agregar una variable

Dos caminos, según si el dato tiene una fuente real en el dominio:

**A) Sin fuente real (siempre el mismo texto o un "no disponible")** — no
toques Python. Escribí directamente en el `.md`:

```
{{NOMBRE_VARIABLE|texto de fallback}}
```

Se resuelve siempre a `texto de fallback`. Usalo para datos que hoy no
tienen de dónde salir (como hoy `RESOLUCION_RECURRIDA` o `DICTAMEN_NUMERO`
en Python) — declararlo en el propio markdown evita una vuelta al adapter.

**B) Con fuente real** (viene del `Expediente`, de una `Obra`, o se calcula) —
sí hace falta tocar Python: agregá la entrada en `vars_map` dentro de
`PlantillaMarkdownAdapter._resolver_variables_expediente`
(`plantilla_markdown_adapter.py:226-350` aprox.). Reglas duras de ese mapeo:

- El fallback de un dato que puede faltar es siempre un marcador explícito
  (`ALGO_NO_DISPONIBLE`, `FOJA_NO_DISPONIBLE`...) — **nunca** un valor
  inventado. Excepción documentada: las firmas y el Vocal Relator, que usan
  el nombre real de la Sala actual (`_FIRMAS_SALA_ACTUAL`, un solo lugar)
  porque es un dato institucional conocido, no un dato del caso.
- Antes de agregar una variable nueva, revisá si ya existe una equivalente
  (p. ej. `RECURRENTE` y `PROCESADO_GRADO_Y_NOMBRE` ya cubren "nombre del
  procesado/recurrente" en distintos contextos).

## Agregar un condicional

Los condicionales (`{{CONDICIONAL_*: SI_...}}`) sí necesitan código: la
lógica de qué texto renderizar vive en
`PlantillaMarkdownAdapter._resolver_condicionales` (mismo archivo,
`:330-395` aprox.). Agregá el `if "CONDICIONAL_X: SI_Y" in plantilla:` con
el texto a inyectar, siguiendo el patrón de los condicionales existentes
(`CONDICIONAL_LOGICA_VIAS`, `CONDICIONAL_LOGICA_SANEAMIENTO`). Esto es lo
único que esta versión del adapter no resuelve sin tocar Python — no hay
sintaxis en markdown para expresar una condición.

## Notas de diseño

Las notas para humanos van acá, nunca dentro de la plantilla: todo el `.md`
llega al LLM (sin marca `[SYSTEM]` va entero como mensaje de usuario), y
una nota al final queda justo después de la consulta.

- `consulta_simple.md`: si el expediente activo tiene obrados cargados y el
  paso 1 detecta que la consulta los requiere, se podría anteponer un
  bloque `[INFORMACIÓN DEL EXPEDIENTE ACTIVO]` con el número de expediente.
  Hoy no se hace: por su naturaleza consultiva, en la mayoría de los casos
  el contexto expandido ya incluye las referencias a los obrados. Si se
  implementa, la variable tiene que resolverse en el adapter (hoy
  `consulta_simple` no pasa por `vars_map`).

## Verificar que no queda nada suelto

- Si te queda una `{{VARIABLE}}` sin resolver (ni en `vars_map` ni con
  `|fallback` inline), el adapter lo loguea como warning al llamar
  `resolver()` — antes viajaba literal al prompt en silencio. Los 4 slots
  que `GenerarBorrador` llena después de `resolver()`
  (`contexto_expandido`, `sugerencia_argumentacion`, `criterio_vocal`,
  `consulta_usuario`) no cuentan como huérfanos.
- Corré los tests de la plantilla que tocaste:
  `uv run pytest backend/tests/unit/test_plantilla_auto_vista_consulta.py
backend/tests/unit/test_plantilla_auto_vista_apelacion.py
backend/tests/borradores/test_resolvedor_plantilla.py -q --no-cov`
