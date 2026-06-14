# Skill: Document Processing (PDF + Imágenes)

## Descripción

Esta skill cubre la extracción de texto desde archivos PDF e imágenes usando la tool `extract_text`. El pipeline está diseñado para ser eficiente en hardware limitado (Celeron N4020, 4GB RAM) priorizando métodos nativos antes de caer en OCR.

## Pipeline de extracción

```
Archivo
  │
  ├── 📄 PDF
  │     ├── ¿Tiene texto nativo?  → PyMuPDF (instantáneo)
  │     └── ¿Escaneado/sin texto? → Tesseract OCR página por página
  │
  └── 🖼️ Imagen (PNG, JPG, TIFF, BMP, WebP)
        └── Tesseract OCR directo
```

## Formatos soportados

| Formato | Extensiones | Método | Velocidad |
|---------|-------------|--------|-----------|
| PDF (nativo) | .pdf | PyMuPDF | ⚡ Instantáneo |
| PDF (escaneado) | .pdf | Tesseract OCR | 🐢 Lento (1-5s x página) |
| Imagen | .png, .jpg, .jpeg, .tiff, .tif, .bmp, .webp | Tesseract OCR | ⚡ Rápido |

## Herramientas relacionadas

- `extract_text` — Tool principal para extraer texto
- `read_file` — Para leer archivos de texto plano ya extraídos

## Limitaciones

- **OCR no es perfecto**: Tesseract funciona bien con textos limpios e impresos, pero puede fallar con:
  - Letra manuscrita
  - Textos muy pequeños (< 10px)
  - Fondos con mucho ruido visual
  - Idiomas no soportados (solo spa+eng por defecto)
- **PDFs escaneados pesados**: El OCR página por página consume CPU y puede tardar en documentos largos (>20 páginas).
- **Sin procesamiento en la nube**: No depende de APIs externas, todo es local.

## Buenas prácticas

1. Si el PDF tiene texto seleccionable, `extract_text` lo detecta automáticamente y no usa OCR.
2. Para imágenes con texto chico, aumentá la resolución antes de pasarle el archivo.
3. Si el texto sale mal con OCR, se puede mejorar con preprocesamiento: convertir a blanco y negro, aumentar contraste, etc. (no implementado aún).
4. Siempre verificá el resultado — el OCR puede alucinar caracteres.

## Futuro (roadmap)

- **Google Cloud Vision API** como fallback cloud cuando haya crédito (más preciso que Tesseract)
- **Preprocesamiento de imágenes** (threshold, deskew, denoise) antes de OCR
- **Extracción de tablas** con estructura
- **Surya OCR** si se consigue GPU o mejora el rendimiento en CPU
