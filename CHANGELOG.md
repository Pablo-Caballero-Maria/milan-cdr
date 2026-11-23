# Registro de cambios

Todos los cambios relevantes de milan-cdr se anotan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/). Cada versión tiene su etiqueta (`vX.Y.Z`) en el
repositorio.

## [Sin publicar]

## [1.1.0] - 2026-11-22

### Añadido

- **Consultas tipadas**: `documents.py` declara el documento de cada colección como un `TypedDict`
  (`CDRDocument`, con los campos de actividad opcionales; `CellDocument` y `CellHourDocument`, las colecciones de
  los apartados 6 y 7) y da cada colección como un `Collection[...]` de PyMongo de ese tipo; cada etapa de un
  pipeline es un `TypedDict` de su operador (`$match`, `$group`, `$facet`, `$out`…). `ty` comprueba así los
  documentos que se insertan, los campos que se leen de los resultados (encontró que el mapa de la cuadrícula
  recibe la proyección `{_id, total}`, ahora `CellTotal`) y los operadores de cada etapa. Los pipelines no
  cambian: siguen siendo los mismos diccionarios que en `mongosh` y que en la memoria.
- Tests del esquema y de las etapas (87 en total).

## [1.0.1] - 2026-11-21

### Cambiado

- La memoria pasa a [`memoria/memoria.pdf`](memoria/memoria.pdf), como en los demás proyectos (es la
  versión final del documento de Google Docs, idéntica a la entregada como `CDRMilan.pdf`), y el material
  de la asignatura a [`instrucciones/`](instrucciones/) (`enunciado.pdf` y `BaseDeDatosCDRMilan.pdf`).

## [1.0.0] - 2026-11-21

### Añadido

- Integración continua con GitHub Actions en cada *push* y *pull request*: Ruff (lint y formato), ty,
  pytest con cobertura contra un MongoDB 8 real (resumen en cada ejecución e insignia en el README) y
  construcción del paquete con `uv build`, comprobando que la CLI se instala y arranca.
- Seguridad: análisis con CodeQL, Dependabot (uv y GitHub Actions), escaneo de secretos con protección
  al hacer *push* y [política de seguridad](SECURITY.md) con avisos privados.
- Licencia [MIT](LICENSE) para el código, [código de conducta](CODE_OF_CONDUCT.md),
  [CITATION.cff](CITATION.cff), plantillas de *issues* (error, mejora y resultado que no coincide con la
  memoria) y de *pull request*.
- [Wiki](https://github.com/Pablo-Caballero-Maria/milan-cdr/wiki) con el conjunto de datos, la carga,
  los apartados 2 a 8, los resultados y el desarrollo.

### Cambiado

- README reorganizado, con insignias, índice, diagramas y figuras de los resultados.

## [0.2.0] - 2026-11-19

### Añadido

- La memoria del trabajo en PDF (`CDRMilan.pdf`, hoy en [`memoria/memoria.pdf`](memoria/memoria.pdf)).

## [0.1.0] - 2026-11-13

### Añadido

- CLI `milan-cdr` (typer): descarga desde Harvard Dataverse, carga en paralelo de los 36,4 millones de
  registros de la semana del 2 al 8 de diciembre de 2013 (siete procesos, lotes de 20 000 documentos),
  los apartados 2 a 8 con pipelines de agregación, el estudio de ocho celdas, las figuras con Plotly y
  el informe en JSON y Markdown (`results/`).
- Tests unitarios, *doctests* y de integración contra MongoDB; Ruff y ty.

[Sin publicar]: https://github.com/Pablo-Caballero-Maria/milan-cdr/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Pablo-Caballero-Maria/milan-cdr/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/Pablo-Caballero-Maria/milan-cdr/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Pablo-Caballero-Maria/milan-cdr/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/Pablo-Caballero-Maria/milan-cdr/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Pablo-Caballero-Maria/milan-cdr/releases/tag/v0.1.0
