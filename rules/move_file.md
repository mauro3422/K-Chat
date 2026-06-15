# move_file

Mueve o copia archivos y directorios.

## Parametros
- `source` (requerido): origen
- `dest` (requerido): destino
- `operation` (opcional): "move" (default) o "copy"

## Comportamiento
- Crea directorios destino si no existen
- NO sobreescribe archivos existentes (seguridad)
- Si destino es un directorio existente, pega el nombre del origen
- Usa `shutil.move` para move, `shutil.copy2`/`copytree` para copy

## Limites
- No soporta wildcards/glob (usar execute_command para eso)
- No soporta sobreescritura forzada
