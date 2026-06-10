# Chrome DevTools MCP — Referencia

> **¿Qué es?** Un servidor MCP (Model Context Protocol) de Google que permite a agentes de IA controlar y inspeccionar un navegador Chrome en vivo.
>
> **¿Sirve para Kairos?** No directamente — Kairos es un chatbot standalone, no un MCP client. Pero SÍ es útil para tu workflow de desarrollo: podés usarlo con OpenCode/Claude/Cursor para debuggear el frontend de Kairos en tiempo real.

## Links

- **GitHub**: https://github.com/ChromeDevTools/chrome-devtools-mcp
- **Docs Chrome**: https://developer.chrome.com/docs/devtools/agents/get-started
- **Tool Reference**: https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/tool-reference.md
- **npm**: `chrome-devtools-mcp`

## Qué hace

Conecta un agente de IA a una instancia de Chrome activa vía MCP. El agente puede:
- **Automatizar inputs**: click, drag, fill, type_text, hover, press_key
- **Navegar**: open_page, navigate_page, close_page, wait_for
- **Debuggear**: evaluate_script, take_screenshot, list_console_messages
- **Performance**: performance_start_trace, performance_stop_trace, lighthouse_audit
- **Red**: list_network_requests, get_network_request
- **Memoria**: take_heapsnapshot, get_heapsnapshot_summary
- **Emular**: emulate (devices), resize_page
- **Extensions**: install_extension, list_extensions

## Cómo se instala (para usar con OpenCode)

Agregar a `~/.config/opencode/opencode.json`:
```json
{
  "mcp": {
    "chrome-devtools": {
      "type": "local",
      "command": ["npx", "-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

## Configuración útil

- `--headless`: Sin ventana visible (para CI/testing)
- `--autoConnect`: Conectar a Chrome ya abierto (Chrome 144+)
- `--browser-url=http://127.0.0.1:9222`: Conectar a instancia específica
- `--isolated`: Perfil temporal limpiado al cerrar

## Uso con Kairos

No es una skill de Kairos. Es una herramienta para tu **workflow de desarrollo**:
1. Abrís Chrome con Kairos corriendo (`http://localhost:8000`)
2. Conectás OpenCode/Claude al Chrome DevTools MCP
3. Le pedís al agente: "Testea el chat de Kairos en http://localhost:8000"
4. El agente abre Chrome, navega, interactúa, y reporta errores

## Categorías de tools (46 total)

| Categoría | Tools | Ejemplo |
|-----------|-------|---------|
| Input | 10 | click, fill, type_text, drag |
| Navigation | 6 | navigate_page, new_page, wait_for |
| Performance | 3 | start_trace, stop_trace, analyze_insight |
| Network | 2 | list_requests, get_request |
| Debugging | 8 | evaluate_script, screenshot, console_messages |
| Memory | 8 | heapsnapshot, class_nodes, retainer_paths |
| Emulation | 2 | emulate (devices), resize_page |
| Extensions | 5 | install, list, reload, trigger, uninstall |
| WebMCP | 2 | execute_tool, list_tools |
