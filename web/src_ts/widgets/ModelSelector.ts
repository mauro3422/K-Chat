import { getLogger } from '../core/infra/LoggerFactory';
import { ILogger } from '../core/infra/Logger';

interface ModelMeta {
  id: string;
  name: string;
  ctx: string | null;
  out: string | null;
  caps: string[];
  cooldown?: number;
}

type Tier = 'go_premium' | 'go_standard' | 'go_economy' | 'free_ratelimited';
type ModelsByTier = Record<Tier, ModelMeta[]>;

const TIER_LABELS: Record<Tier, string> = {
  go_premium: 'GO Premium',
  go_standard: 'GO Standard',
  go_economy: 'GO Económico',
  free_ratelimited: 'Free (rate-limited)',
};

// Colored status dot SVGs per tier
const TIER_DOTS: Record<Tier, string> = {
  go_premium: `<svg viewBox="0 0 10 10" width="10" height="10"><circle cx="5" cy="5" r="4" fill="#f0883e"/></svg>`,
  go_standard: `<svg viewBox="0 0 10 10" width="10" height="10"><circle cx="5" cy="5" r="4" fill="#58a6ff"/></svg>`,
  go_economy: `<svg viewBox="0 0 10 10" width="10" height="10"><circle cx="5" cy="5" r="4" fill="#3fb950"/></svg>`,
  free_ratelimited: `<svg viewBox="0 0 10 10" width="10" height="10"><circle cx="5" cy="5" r="4" fill="#f5c542"/></svg>`,
};

const CAP_ICONS: Record<string, string> = {
  reasoning: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2a3 3 0 0 0-3 3v0a3 3 0 0 0 3 3v0a3 3 0 0 0 3-3v0a3 3 0 0 0-3-3z"/><path d="M5 8v1a3 3 0 0 0 3 3h0a3 3 0 0 0 3-3V8"/><path d="M6.5 12v1.5"/><path d="M9.5 12v1.5"/><path d="M6 14.5h4"/><circle cx="8" cy="4.5" r="0.8" fill="currentColor" stroke="none"/></svg>`,
  toolcall: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 2.5l3 3-5 5-3-3 5-5z"/><path d="M8.5 4.5l-4 4"/><path d="M2.5 13.5l3-3"/><path d="M5.5 10.5l-2 2"/><circle cx="11" cy="4" r="0.6" fill="currentColor" stroke="none"/></svg>`,
  image: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="2.5" width="14" height="11" rx="1.5"/><circle cx="5.5" cy="6" r="1.5"/><path d="M1 11.5l3.5-3 2.5 2 3-3 4 4"/></svg>`,
  video: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="3" width="10" height="10" rx="1.5"/><polygon points="11,5.5 15,3.5 15,12.5 11,10.5"/></svg>`,
  audio: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 6.5v3a3 3 0 0 0 6 0v-3"/><rect x="5" y="1.5" width="6" height="8" rx="1"/><path d="M8 11.5v3"/><path d="M5.5 14.5h5"/></svg>`,
};

const CAP_TITLES: Record<string, string> = {
  reasoning: 'Razonamiento',
  toolcall: 'Herramientas',
  image: 'Imagen',
  video: 'Video',
  audio: 'Audio',
};

export class ModelSelector {
  private triggerEl: HTMLElement | null = null;
  private currentEl: HTMLElement | null = null;
  private dropdownEl: HTMLElement | null = null;
  private hiddenSelect: HTMLSelectElement | null = null;
  private models: ModelsByTier = { go_premium: [], go_standard: [], go_economy: [], free_ratelimited: [] };
  private selectedId = '';
  private _serverDefaultModel = '';
  private _clickCb: ((e: MouseEvent) => void) | null = null;
  private logger: ILogger = getLogger('model-selector');

  init(): void {
    this.triggerEl = document.getElementById('model-select-trigger');
    this.currentEl = document.getElementById('model-select-current');
    this.dropdownEl = document.getElementById('model-select-dropdown');
    this.hiddenSelect = document.getElementById('model-select') as HTMLSelectElement;

    if (!this.triggerEl || !this.currentEl || !this.dropdownEl) {
      this.logger.warn('model_selector_missing_dom');
      if (this.currentEl) this.currentEl.textContent = 'Selector unavailable';
      return;
    }

    this.loadModels();
    this.render();
    this.attachEvents();
  }

  private loadModels(): void {
    const script = document.getElementById('model-data');
    if (!script) return;
    try {
      const data = JSON.parse(script.textContent || '{}') as ModelsByTier;
      this.models = data;
      // Read server-declared default model from data attribute
      const defaultModel = (script as HTMLElement).dataset.defaultModel || '';
      if (defaultModel) {
        this._serverDefaultModel = defaultModel;
      }
      this.populateHiddenSelect();
    } catch {
      this.logger.warn('failed_to_parse_model_data');
      this.models = { go_premium: [], go_standard: [], go_economy: [], free_ratelimited: [] };
      this.render();
      if (this.currentEl) this.currentEl.textContent = 'Error loading models';
    }
  }

  private populateHiddenSelect(): void {
    if (!this.hiddenSelect) return;
    this.hiddenSelect.innerHTML = '';
    for (const models of Object.values(this.models)) {
      for (const m of models) {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.name;
        this.hiddenSelect.appendChild(opt);
      }
    }
  }

  private render(): void {
    if (!this.dropdownEl || !this.currentEl) return;

    // Pick from localStorage, then server default, then hidden select, then first available
    const allModels = Object.values(this.models).flat();
    if (allModels.length === 0) {
      this.currentEl.textContent = 'No models available';
      return;
    }

    this.selectedId =
      localStorage.getItem('selected_model') ||
      this._serverDefaultModel ||
      this.hiddenSelect?.value ||
      allModels[0]?.id ||
      '';
    this.logger.info('default_model', `selected=${this.selectedId} serverDefault=${this._serverDefaultModel}`);
    this.updateCurrent();
    // Sync hidden select
    if (this.hiddenSelect) this.hiddenSelect.value = this.selectedId;
    // Expose globally for ChatForm
    try { (window as any).__k = (window as any).__k || {}; (window as any).__k.selectedModel = this.selectedId; } catch {}

    // Build dropdown content
    const frag = document.createDocumentFragment();
    for (const [tier, models] of Object.entries(this.models)) {
      if (models.length === 0) continue;
      frag.appendChild(this.renderGroup(tier as Tier, models));
    }
    this.dropdownEl.innerHTML = '';
    this.dropdownEl.appendChild(frag);
  }

  private renderGroup(tier: Tier, models: ModelMeta[]): HTMLElement {
    const group = document.createElement('div');
    group.className = 'ms-group';

    const label = document.createElement('div');
    label.className = 'ms-group-label';
    label.textContent = TIER_LABELS[tier] || tier;
    group.appendChild(label);

    for (const m of models) {
      try {
        const item = document.createElement('div');
        item.className = `ms-item ms-tier-${tier} ${m.id === this.selectedId ? 'ms-item-selected' : ''}`;
        item.dataset.modelId = m.id;

        // Status dot
        const dotEl = document.createElement('span');
        dotEl.className = 'ms-item-dot';
        dotEl.innerHTML = TIER_DOTS[tier] || '';
        item.appendChild(dotEl);

        // Model name
        const nameEl = document.createElement('span');
        nameEl.className = 'ms-item-name';
        nameEl.textContent = m.name;
        item.appendChild(nameEl);

        // Limits
        if (m.ctx || m.out) {
          const limits = document.createElement('span');
          limits.className = 'ms-item-limits';
          const parts: string[] = [];
          if (m.ctx) parts.push(`${m.ctx} ctx`);
          if (m.out) parts.push(`${m.out} out`);
          limits.textContent = '· ' + parts.join(' · ');
          item.appendChild(limits);
        }

        // Capability SVGs
        const capsEl = document.createElement('span');
        capsEl.className = 'ms-item-caps';
        if (m.caps && m.caps.length > 0) {
          for (const cap of m.caps) {
            const icon = CAP_ICONS[cap];
            if (icon) {
              const wrapper = document.createElement('span');
              wrapper.className = 'ms-cap-icon';
              wrapper.title = CAP_TITLES[cap] || cap;
              try {
                wrapper.innerHTML = icon;
              } catch {
                wrapper.textContent = CAP_TITLES[cap] || cap;
              }
              capsEl.appendChild(wrapper);
            } else {
              const fallback = document.createElement('span');
              fallback.className = 'ms-cap-fallback';
              fallback.textContent = `(${cap})`;
              capsEl.appendChild(fallback);
            }
          }
        }
        // Cooldown badge
        if (m.cooldown) {
          const cd = document.createElement('span');
          cd.className = 'ms-item-cooldown';
          cd.textContent = `🔒 ${m.cooldown}s`;
          capsEl.appendChild(cd);
        }
        item.appendChild(capsEl);

        item.addEventListener('click', () => this.select(m.id));
        group.appendChild(item);
      } catch (err) {
        this.logger.warn('render_group_item_error', String(err));
      }
    }

    return group;
  }

  private updateCurrent(): void {
    if (!this.currentEl) return;
    for (const models of Object.values(this.models)) {
      const found = models.find(m => m.id === this.selectedId);
      if (found) {
        this.currentEl.textContent = found.name;
        return;
      }
    }
    this.currentEl.textContent = this.selectedId || 'Seleccionar modelo';
  }

  private select(id: string): void {
    if (id === this.selectedId) return;
    this.selectedId = id;
    this.updateCurrent();
    this.close();

    // Persist to localStorage
    localStorage.setItem('selected_model', id);

    // Expose globally for ChatForm to read
    try { (window as any).__k = (window as any).__k || {}; (window as any).__k.selectedModel = id; } catch {}

    // Update hidden select and trigger change event
    if (this.hiddenSelect) {
      this.hiddenSelect.value = id;
      this.hiddenSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // Update visual selection in dropdown items
    if (this.dropdownEl) {
      this.dropdownEl.querySelectorAll('.ms-item').forEach(el => {
        el.classList.toggle(
          'ms-item-selected',
          (el as HTMLElement).dataset.modelId === id,
        );
      });
    }

    this.logger.info('select', `model=${id}`);
  }

  get selected(): string {
    return this.selectedId;
  }

  private attachEvents(): void {
    this.triggerEl?.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      this.toggle();
    });

    this._clickCb = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        this.dropdownEl &&
        !this.dropdownEl.contains(target) &&
        target !== this.triggerEl &&
        !this.triggerEl?.contains(target)
      ) {
        this.close();
      }
    };
    document.addEventListener('click', this._clickCb);
  }

  private toggle(): void {
    if (!this.dropdownEl) return;
    const isOpen = this.dropdownEl.style.display !== 'none';
    if (isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  private open(): void {
    if (!this.dropdownEl || !this.triggerEl) return;
    // Detect if there's enough space below
    const rect = this.triggerEl.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const dropdownHeight = Math.min(360, window.innerHeight * 0.5);
    if (spaceBelow < dropdownHeight && spaceAbove > spaceBelow) {
      this.dropdownEl.classList.add('ms-drop-up');
      this.dropdownEl.classList.remove('ms-drop-down');
    } else {
      this.dropdownEl.classList.add('ms-drop-down');
      this.dropdownEl.classList.remove('ms-drop-up');
    }
    this.dropdownEl.style.display = 'block';
    this.triggerEl.classList.add('ms-open');
    this.logger.info('open', `dir=${spaceBelow < dropdownHeight ? 'up' : 'down'}`);
  }

  private close(): void {
    if (!this.dropdownEl) return;
    this.dropdownEl.style.display = 'none';
    this.triggerEl?.classList.remove('ms-open');
  }

  setModel(id: string): void {
    this.select(id);
  }

  dispose(): void {
    if (this._clickCb) document.removeEventListener('click', this._clickCb);
  }
}
