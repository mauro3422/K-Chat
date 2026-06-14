# extract_text
**Extrae el texto de uno o más archivos (PDF, PNG, JPG, JPEG, TIFF, BMP). Para PDFs con texto nativo lo extrae directamente. Para PDFs escaneados o imágenes usa OCR (Tesseract). Devuelve el texto extraído de cada archivo separado por un encabezado.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `files` | array | Sí |  | Lista de rutas de archivos a procesar (máx. 10). |
