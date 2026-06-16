import { StreamEvent, StreamEventType, SimulatorConfig, ToolCallPayload } from '../types/streaming';
import { randomWidget, allWidgetsBlock, clockWidget, counterWidget, accordionWidget, notesWidget, miniDashboardWidget, weatherWidget } from '../widgets/templates';

/**
 * StreamSimulator — generates realistic NDJSON-like events dynamically.
 *
 * Instead of hardcoded text, it uses the user's message as a "prompt"
 * to generate varied reasoning, tool calls, content, and optionally widgets.
 *
 * Each call to generate() returns an array of events with realistic timing.
 *
 * Includes error simulation: ~15% chance of random error events,
 * and 100% when intent is 'error'.
 */

export interface ErrorScenario {
  type: string;
  message: string;
  httpStatus?: number;
}

const ERROR_SCENARIOS: ErrorScenario[] = [
  { type: 'rate_limit', message: 'Límite de tokens excedido. Esperá 30 segundos.', httpStatus: 429 },
  { type: 'rate_limit', message: 'Demasiadas solicitudes. Límite: 10 req/min.', httpStatus: 429 },
  { type: 'rate_limit', message: 'Free tier: 5 requests por hora. Volvé en 12 minutos.', httpStatus: 429 },
  { type: 'auth', message: 'API key inválida o expirada. Verificá tu configuración.', httpStatus: 401 },
  { type: 'auth', message: 'Token de autenticación no válido.', httpStatus: 401 },
  { type: 'server', message: 'El proveedor de IA está caído. Intentá de nuevo.', httpStatus: 502 },
  { type: 'server', message: 'Error interno del servidor.', httpStatus: 500 },
  { type: 'server', message: 'Tiempo de espera agotado (timeout 30s).', httpStatus: 504 },
  { type: 'network', message: 'Conexión perdida con el servidor.', httpStatus: 0 },
  { type: 'network', message: 'No se pudo establecer conexión segura (TLS).', httpStatus: 0 },
  { type: 'model', message: 'El modelo DeepSeek V3 no está disponible en este momento.', httpStatus: 503 },
  { type: 'model', message: 'Contexto demasiado largo. Reducí el mensaje.', httpStatus: 413 },
  { type: 'tool_error', message: 'La herramienta web_search falló: timeout en la búsqueda.' },
  { type: 'tool_error', message: 'La herramienta read_file falló: archivo no encontrado.' },
  { type: 'empty_response', message: 'El modelo generó una respuesta vacía. Intentá reformular.' },
];

export class StreamSimulator {
  /** Pool of tool names to randomly pick from */
  private static TOOLS = [
    'search_files', 'read_file', 'web_search', 'fetch_url',
    'analyze_code', 'list_files', 'grep_search', 'git_log',
    'widget_create', 'memory_search', 'db_query', 'run_code',
  ];

  /** Pool of reasoning fragments for Phase 1 (initial analysis) */
  private static REASONING_P1 = [
    'Analizando la consulta del usuario para determinar el contexto y los archivos relevantes...',
    'Procesando la solicitud. Iniciando búsqueda en la base de conocimiento local...',
    'Interpretando la pregunta. Voy a revisar los módulos del sistema involucrados...',
    'Evaluando la mejor estrategia para responder. Revisando documentación disponible...',
    'Iniciando análisis. Identificando patrones y componentes relacionados en el código...',
  ];

  /** Pool of reasoning fragments for Phase 2 (after first tool) */
  private static REASONING_P2 = [
    'Procesando los resultados obtenidos. Identificando la estructura y relaciones entre componentes...',
    'Analizando la información recuperada. Extrayendo los puntos clave para la respuesta...',
    'Revisando los datos encontrados. Correlacionando con el contexto de la conversación...',
    'Evaluando los archivos identificados. Determinando su relevancia para la respuesta final...',
    'Sintetizando la información disponible. Preparando la estructura de la respuesta...',
  ];

  /** Pool of reasoning fragments for Phase 3 (final formulation) */
  private static REASONING_P3 = [
    'Formulando la respuesta final con base en toda la información recolectada...',
    'Estructurando la respuesta de forma clara y organizada para el usuario...',
    'Componiendo el mensaje final integrando los hallazgos de todas las fases anteriores...',
    'Preparando el resumen ejecutivo con los puntos más importantes del análisis...',
    'Finalizando el razonamiento. Generando el contenido formateado para mostrar al usuario...',
  ];

  /** Pool of memory fragments */
  private static MEMORIES = [
    'El usuario previamente solicitó mejoras visuales en el frontend TypeScript.',
    'Recordar que el proyecto K-Chat utiliza una arquitectura de bloques Lego desacoplada.',
    'Sesión anterior: el usuario estaba trabajando en la migración de widgets a TypeScript.',
    'El usuario prefiere mantener la compatibilidad con el sistema de temas light/dark existente.',
    'Contexto: el proyecto usa Vite como bundler y TypeScript 6+ para tipado estricto.',
  ];

  /** Pool of success result texts for tool calls */
  private static TOOL_RESULTS: Record<string, string[]> = {
    search_files: [
      'Encontrados 12 archivos relevantes en el proyecto.',
      'Se identificaron 5 módulos principales que coinciden con el patrón de búsqueda.',
      'Hallados 8 resultados. Los más relevantes están en web/src_ts/ y web/static/modules/.',
    ],
    read_file: [
      'Archivo leído correctamente. Contenido cargado en memoria para análisis.',
      'Documento procesado. Se extrajeron las definiciones de tipos e interfaces.',
      'Código fuente analizado. Estructura de clases y métodos identificada.',
    ],
    web_search: [
      'Búsqueda web completada. 3 resultados relevantes encontrados.',
      'Información recuperada de 2 fuentes. Datos actualizados al momento.',
    ],
    analyze_code: [
      'Análisis estructural completado. Se identificaron patrones de diseño y posibles mejoras.',
      'Código analizado. La arquitectura sigue principios de inyección de dependencias y desacoplamiento.',
    ],
    fetch_url: [
      'URL cargada exitosamente. Contenido parseado y listo para procesar.',
      'Página web obtenida. Se extrajo el contenido principal del documento.',
    ],
    widget_create: [
      'Widget generado correctamente. Código HTML listo para incrustar.',
      'Widget interactivo creado. Incluye estilos y lógica JavaScript embebida.',
    ],
  };

  private static DEFAULT_RESULT = 'Operación completada exitosamente.';

  /** Probability (0-1) of simulating an error event instead of normal content completion */
  static readonly ERROR_CHANCE = 0.15;

  /** Generate a random error event from a scenario */
  static generateError(): StreamEvent {
    const scenario = ERROR_SCENARIOS[Math.floor(Math.random() * ERROR_SCENARIOS.length)];
    return {
      t: 'error',
      d: JSON.stringify({ type: scenario.type, message: scenario.message, httpStatus: scenario.httpStatus }),
    };
  }

  /**
   * Generate a sequence of stream events based on a user message.
   * Returns an array of { t, d } events and a recommended delay between them.
   */
  generate(userMessage: string, config?: SimulatorConfig): StreamEvent[] {
    const cfg = config || this.detectIntent(userMessage);
    const events: StreamEvent[] = [];

    // Memory phase: inject retrieved memories
    const memory = this.pickRandom(StreamSimulator.MEMORIES);
    events.push(...this.tokenizeEvent('memory', memory));

    // Phase 1: Reasoning
    const reasoning1 = this.pickRandom(StreamSimulator.REASONING_P1);
    events.push(...this.tokenizeEvent('reasoning', reasoning1));

    // Tool 1: search_files (calling → ok)
    const tool1 = this.pickRandom(StreamSimulator.TOOLS);
    events.push({
      t: 'tool_call',
      d: JSON.stringify({ status: 'calling', name: tool1 } satisfies ToolCallPayload),
    });
    events.push(...this.toolResultEvents(tool1, 'ok'));

    // Phase 2: Reasoning
    const reasoning2 = this.pickRandom(StreamSimulator.REASONING_P2);
    events.push(...this.tokenizeEvent('reasoning', reasoning2));

    // Tool 2: different tool (calling → ok)
    const tool2 = this.pickRandom(StreamSimulator.TOOLS.filter(t => t !== tool1));
    events.push({
      t: 'tool_call',
      d: JSON.stringify({ status: 'calling', name: tool2 } satisfies ToolCallPayload),
    });
    events.push(...this.toolResultEvents(tool2, 'ok'));

    // Phase 3: Final reasoning
    const reasoning3 = this.pickRandom(StreamSimulator.REASONING_P3);
    events.push(...this.tokenizeEvent('reasoning', reasoning3));

    // Error simulation: 100% when intent is 'error', or ~15% random chance
    const shouldError = cfg.intent === 'error' || Math.random() < StreamSimulator.ERROR_CHANCE;

    if (shouldError) {
      events.push(StreamSimulator.generateError());
    } else {
      // Content: the main response
      const content = this.buildContent(userMessage, cfg, tool1, tool2);
      events.push(...this.tokenizeEvent('content', content));
    }

    return events;
  }

  /**
   * Generate with optional widget inclusion.
   */
  generateWithWidget(userMessage: string): StreamEvent[] {
    const events = this.generate(userMessage, { includeWidget: true, toolCount: 2 });
    return events;
  }

  /**
   * Generate a response that includes a widget code block.
   */
  generateWidgetDemo(userMessage: string): StreamEvent[] {
    const widgetCode = randomWidget();
    const events: StreamEvent[] = [];

    const reasoning1 = 'El usuario solicita un widget interactivo. Voy a generar el código HTML con estilos y lógica embehidos...';
    events.push(...this.tokenizeEvent('reasoning', reasoning1));

    events.push({
      t: 'tool_call',
      d: JSON.stringify({ status: 'calling', name: 'widget_create' } satisfies ToolCallPayload),
    });
    events.push(...this.toolResultEvents('widget_create', 'ok'));

    const reasoning2 = 'Widget generado. Voy a incrustarlo en la respuesta con el bloque markdown correspondiente...';
    events.push(...this.tokenizeEvent('reasoning', reasoning2));

    // The content includes a widget block!
    const content = `Aquí tienes el widget interactivo que generé:\n\n\`\`\`html-widget demo\n${widgetCode}\n\`\`\`\n\n¿Qué te parece? Puedo modificarlo si lo necesitas.`;
    events.push(...this.tokenizeEvent('content', content));

    return events;
  }

  /** Detect intent from the user message keywords — includes common misspellings */
  detectIntent(userMessage: string): SimulatorConfig {
    const msg = userMessage.toLowerCase().replace(/[^a-záéíóúñ\s]/g, '');
    // Split into words for more flexible matching
    const words = msg.split(/\s+/).filter(Boolean);

    // Helper: check if any word is in a list
    const hasAny = (keywords: string[]) => keywords.some(k => words.includes(k) || msg.includes(k));

    // Spellings variants for 'widget'
    const widgetVariants = ['widget', 'wigdet', 'wiget', 'wdiget', 'widgdet', 'whidget', 'whitget', 'widjet', 'wichit'];

    if (hasAny([...widgetVariants, 'clock', 'contador', 'dash', 'acorde', 'acordeon', 'nota', 'notas', 'todos', 'tres'])) {
      return { intent: 'widget', includeWidget: true, toolCount: 2 };
    }
    if (hasAny(['markdown', 'video', 'imagen', 'imágen', 'tabla', 'complejo', 'multimedia', 'formato'])) {
      return { intent: 'rich_markdown', includeWidget: true, toolCount: 2 };
    }
    if (hasAny(['error', 'falla', 'fallo', 'bug', 'broken', 'mal'])) {
      return { intent: 'error', includeWidget: false, toolCount: 3 };
    }
    if (hasAny(['analiza', 'analizar', 'busca', 'buscar', 'investiga', 'investigar', 'codigo', 'código', 'explora', 'explorar'])) {
      return { intent: 'research', includeWidget: Math.random() > 0.5, toolCount: 2 };
    }
    return { intent: 'default', includeWidget: Math.random() > 0.7, toolCount: 2 };
  }

  /** Build varied content text with optional widget */
  private buildContent(userMessage: string, cfg: SimulatorConfig, tool1: string, tool2: string): string {
    const greetings = [
      '¡Listo! He procesado tu solicitud.',
      'Perfecto, aquí está el resultado del análisis.',
      'Entendido. Te comparto lo que encontré.',
      '¡Hecho! Esto es lo que pude recopilar:',
    ];
    const greeting = this.pickRandom(greetings);

    const bodies: string[] = [
      `He revisado los módulos del sistema y ejecutado las herramientas necesarias (${tool1}, ${tool2}) para responder a tu consulta.`,
      `Tras analizar la información utilizando ${tool1} y ${tool2}, estos son los resultados obtenidos.`,
      `Utilizando las herramientas disponibles, pude verificar el estado actual del sistema.`,
    ];

    let content = `${greeting}\n\n${this.pickRandom(bodies)}\n\n`;

    // Rich markdown content with tables, images, code blocks, etc.
    if (cfg.intent === 'rich_markdown') {
      content += this.buildRichMarkdownBlock();
    }

    // Optionally include widgets
    if (cfg.includeWidget) {
      if (cfg.intent === 'widget') {
        const widgetIntro = 'Aquí tienes todos los widgets para testear:\n';
        content += `${widgetIntro}\n${allWidgetsBlock(true)}\n\n`;
      } else {
        // Single random widget
        const widgetCode = randomWidget();
        const widgetIntro = this.pickRandom([
          'Además, generé un widget interactivo para visualizar los datos:\n',
          'Aquí tienes un componente visual que creé para la ocasión:\n',
          'Incluyo también este widget dinámico:\n',
        ]);
        content += `${widgetIntro}\`\`\`html-widget\n${widgetCode}\n\`\`\`\n\n`;
      }
    }

    const closings = [
      '¿Necesitas algo más o quieres que ajuste algún detalle?',
      '¿Qué opinas del resultado? Puedo refinarlo si es necesario.',
      'Quedo atento por si requieres información adicional.',
      'Espero que te sea útil. Avísame si necesitas profundizar en algo.',
    ];
    content += this.pickRandom(closings);

    return content;
  }

  /** Generate rich markdown content with tables, images, code blocks, and an embedded widget */
  private buildRichMarkdownBlock(): string {
    const pages = [
      {
        title: '📊 Análisis de Rendimiento',
        intro: 'A continuación, te presento un análisis detallado en formato tabular con los datos recopilados de las últimas 24 horas:',
        table: `| Métrica | Valor | Promedio | Status |
|---------|-------|----------|--------|
| **CPU** | 67% | 52% | 🟡 Moderado |
| **RAM** | 4.2 GB | 3.8 GB | 🟢 Normal |
| **Disk I/O** | 245 MB/s | 180 MB/s | 🔴 Alto |
| **Network** | 1.2 Gbps | 0.8 Gbps | 🟢 Normal |
| **Latencia** | 42 ms | 38 ms | 🟢 Normal |`,
        extra: `Además, aquí tienes un **gráfico interactivo** que generé con los datos en tiempo real:\n\n`,
        widget: true,
      },
      {
        title: '🖼️ Documentación Visual',
        intro: 'Aquí tienes algunos ejemplos de cómo se renderizan los diferentes elementos multimedia en K-Chat:',
        table: `| Tipo | Descripción | Preview |
|------|-------------|---------|
| **Imagen pequeña** | Icono de 32×32 | ![K-Chat](https://via.placeholder.com/32x32/58a6ff/ffffff?text=K) |
| **Imagen mediana** | Screenshot 400×200 | ![Preview](https://via.placeholder.com/400x200/1c2333/58a6ff?text=Dashboard+Preview) |
| **Imagen grande** | Banner 800×200 | ![Banner](https://via.placeholder.com/800x200/0d1117/3fb950?text=K-Chat+TypeScript+Prototype) |
| **Gráfico** | Chart ejemplo | ![Chart](https://via.placeholder.com/600x300/161b22/f0883e?text=📊+Performance+Chart) |`,
        extra: `Y un **video embebido** de demostración (placeholder):\n\n<iframe width="560" height="315" src="https://www.youtube.com/embed/dQw4w9WgXcQ" title="Demo" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>\n\n`,
        widget: false,
      },
      {
        title: '💻 Código de Integración',
        intro: 'Aquí tienes un ejemplo de cómo integrar los diferentes componentes del sistema:',
        table: `| Componente | Archivo | Estado |
|------------|---------|--------|
| **EventBus** | \`core/EventBus.ts\` | ✅ Listo |
| **Widget Detector** | \`core/WidgetDetector.ts\` | ✅ Listo |
| **Iframe Builder** | \`rendering/IframeBuilder.ts\` | ✅ Listo |
| **Canvas** | \`widgets/canvas-workspace.ts\` | 🚧 Pendiente |`,
        extra: `\n\`\`\`typescript
// Ejemplo de uso del EventBus con widgets
const eventBus = new TypedEventBus();
const widgetRegistry = new WidgetRegistry();
const detector = new WidgetDetector(widgetRegistry);

// Escuchar eventos de widget detectados
eventBus.on('widget:detected', (data) => {
  console.log('Widget detectado:', data.key);
  const code = widgetRegistry.getCodeByKey(data.key);
  if (code) {
    renderWidget(code);
  }
});

// Emitir evento de detección
eventBus.emit('widget:detected', { key: 'clock' });
\`\`\`\n
> **Nota**: Este sistema sigue el patrón de bloques Lego — cada pieza es independiente y reemplazable.\n`,
        widget: true,
      },
    ];

    const page = this.pickRandom(pages);
    let markdown = `\n---\n\n### ${page.title}\n\n${page.intro}\n\n${page.table}\n\n${page.extra}`;

    if (page.widget) {
      const w = this.pickRandom([clockWidget, counterWidget, accordionWidget, notesWidget, miniDashboardWidget, weatherWidget]);
      markdown += `\`\`\`html-widget\n${w()}\n\`\`\`\n\n`;
    }

    markdown += `\n---\n\n`;
    return markdown;
  }

  /** Generate tool call events (transform calling→result) */
  private toolResultEvents(toolName: string, status: 'ok' | 'error'): StreamEvent[] {
    const events: StreamEvent[] = [];

    if (status === 'ok') {
      events.push({
        t: 'tool_call',
        d: JSON.stringify({ status: 'ok', name: toolName } satisfies ToolCallPayload),
      });
    } else {
      events.push({
        t: 'tool_call',
        d: JSON.stringify({ status: 'error', name: toolName } satisfies ToolCallPayload),
      });
    }

    return events;
  }

  /** Split text into word-by-word reasoning/content events for realistic streaming */
  private tokenizeEvent(type: StreamEventType, text: string): StreamEvent[] {
    // For reasoning: split by words for word-by-word streaming
    if (type === 'reasoning' || type === 'memory') {
      const words = text.split(' ');
      // Group words into chunks of 1-3 for efficiency
      const chunks: string[] = [];
      let i = 0;
      while (i < words.length) {
        const chunkSize = 1 + Math.floor(Math.random() * 2); // 1-3 words
        chunks.push(words.slice(i, i + chunkSize).join(' ') + ' ');
        i += chunkSize;
      }
      return chunks.map(word => ({ t: type, d: word }));
    }

    // For content: split into slightly larger chunks with newlines preserved
    if (type === 'content') {
      const parts = text.split(/(\n\n)/g);
      return parts.map(part => ({ t: type, d: part }));
    }

    return [{ t: type, d: text }];
  }

  private pickRandom<T>(arr: T[]): T {
    return arr[Math.floor(Math.random() * arr.length)];
  }
}
