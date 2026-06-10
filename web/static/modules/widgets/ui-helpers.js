/**
 * Kairos Widgets — UI Helpers
 *
 * Funciones puras de UI reutilizables.
 */
export function createToolbarButton(config) {
    var btn = document.createElement('button');
    btn.textContent = config.label;
    btn.style.background = config.background || 'transparent';
    btn.style.border = config.border || '1px solid #30363d';
    btn.style.color = config.color || '#8b949e';
    btn.style.padding = config.padding || '2px 6px';
    btn.style.borderRadius = config.borderRadius || '4px';
    btn.style.cursor = 'pointer';
    btn.style.fontSize = config.fontSize || '9px';
    if (config.fontWeight) btn.style.fontWeight = config.fontWeight;
    btn.onclick = config.onClick;
    return btn;
}
