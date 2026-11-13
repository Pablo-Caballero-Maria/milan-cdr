"""Carga y análisis con MongoDB de los CDR de Milán (Telecom Italia Big Data Challenge).

Módulos:

* :mod:`milan_cdr.config`: constantes del dominio y configuración.
* :mod:`milan_cdr.dataverse`: descarga de los ficheros desde Harvard Dataverse.
* :mod:`milan_cdr.parsing`: conversión de líneas ``.txt`` a documentos.
* :mod:`milan_cdr.loader`: carga masiva en MongoDB (apartado 1).
* :mod:`milan_cdr.pipelines`: pipelines de agregación (apartados 2-8).
* :mod:`milan_cdr.analysis`: ejecución de los apartados 2-7.
* :mod:`milan_cdr.study`: estudio de celdas (apartado 8).
* :mod:`milan_cdr.countries`: prefijo telefónico → país.
* :mod:`milan_cdr.plots` / :mod:`milan_cdr.report`: figuras e informe.
* :mod:`milan_cdr.cli`: interfaz de línea de comandos ``milan-cdr``.
"""

__version__ = "0.1.0"
