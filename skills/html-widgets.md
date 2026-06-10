# Habilidad: HTML Widgets Interactivos

Permite al agente generar interfaces interactivas visuales (como calculadoras, planificadores, gráficos o juegos sencillos) directamente en la conversación de chat.

## Formato de Salida
Para generar un widget, debes escribir un bloque de código Markdown utilizando la etiqueta de lenguaje `html-widget`.

* **Widgets Temporales (Borrador)**: Escribe la etiqueta de bloque simple `html-widget`. Se usará como borrador y no activará controles de versión ni edición. Nota: El botón de guardado manual ha sido removido de la UI; debes usar la acción `save_widget` cuando consideres oportuno consolidar y promover un widget.
* **Widgets Oficiales (Versionados)**: Agrega el nombre único del widget en minúsculas y sin espacios al lado de la etiqueta de lenguaje, por ejemplo: `html-widget calculadora` o `html-widget notas`. Esto activa de inmediato el versionado, el editor in-situ y el historial de cambios en la interfaz (permitiendo que el usuario edite y guarde nuevas versiones manualmente).
* **Invocar/Cargar Widgets Guardados**: Si el widget ya ha sido guardado oficialmente en el sistema (lo sabes por tu memoria o usando `get_widget_code`), **NUNCA** vuelvas a imprimir todo su código fuente en tu respuesta de chat. En su lugar, simplemente escribe el tag inline `[Widget: nombre-del-widget]` en tu texto (ej: `Aquí tenés el widget: [Widget: notas-rapidas]`). El sistema detectará esta llamada en tiempo real durante el streaming, recuperará el código de forma asíncrona de la base de datos global y renderizará el widget al instante sin saturar el chat de código repetitivo ni inducir errores de sintaxis.


Todo el contenido de este bloque debe ser código HTML, CSS y JavaScript autocontenido. No debes agregar explicaciones de texto dentro del bloque de código.

Ejemplo de bloque:
```html-widget
<div id="app">
  <!-- Tu estructura HTML aquí -->
</div>
<style>
  /* Tu estilo CSS aquí */
</style>
<script>
  // Tu lógica JavaScript aquí
</script>
```

## Persistencia de Estado
Los widgets pueden persistir su estado para que no se pierdan cuando el usuario recarga la página (F5) o navega por el historial de sesiones.

Para usar la persistencia:
1. **Cargar Estado Inicial**: Al arrancar, el widget puede consultar `window.initialState` (que contendrá el último estado guardado como un objeto de JavaScript, o `null`/`undefined` si es la primera ejecución).
2. **Guardar Nuevo Estado**: Cada vez que el usuario interactúe y cambie el estado (ej. un clic en un botón, un campo de texto modificado), llama a la función expuesta en el iframe:
   `window.saveState(objetoEstado)` (que realiza la persistencia en la base de datos de SQLite en segundo plano de manera transparente).

### Estructura de Ejemplo con Persistencia:
```html-widget
<div id="app" style="text-align: center;">
  <h3>Contador con Persistencia</h3>
  <div id="counter" style="font-size: 2rem; margin: 10px 0; color: #fff;">0</div>
  <button id="btn" style="padding: 8px 16px; border-radius: 8px; cursor: pointer;">Incrementar</button>
</div>
<script>
  // 1. Cargar el estado inicial persistido (si existe) o inicializar por defecto
  const state = window.initialState || { clickCount: 0 };

  // 2. Usar los datos para inicializar la UI
  const counter = document.getElementById('counter');
  const btn = document.getElementById('btn');
  counter.textContent = state.clickCount;

  btn.onclick = () => {
    state.clickCount++;
    counter.textContent = state.clickCount;
    // 3. Guardar el nuevo estado de forma persistente
    window.saveState(state);
  };
</script>
```

## Lineamientos de Diseño
- Usa estilos oscuros modernos (colores HSL fluidos, bordes sutiles, fuentes limpias como system-ui).
- No uses `height: 100vh;` o `width: 100vw;` en las etiquetas `html` o `body`, ya que los widgets corren dentro de un iFrame de altura dinámica. Usa contenedores fluidos que se ajusten al contenido.
- Agrega micro-interacciones (efectos `:hover` y `:active` en botones y tarjetas).
