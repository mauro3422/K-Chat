import { describe, it, expect, afterEach, beforeEach } from 'vitest';
import { ModelSelector } from '../widgets/ModelSelector';

const SAMPLE_MODELS = {
  go_premium: [
    { id: 'premium-v1', name: 'Premium V1', ctx: '32K', out: '4K', caps: ['reasoning', 'toolcall'], cooldown: 0 },
    { id: 'premium-v2', name: 'Premium V2', ctx: '128K', out: '8K', caps: ['reasoning', 'toolcall', 'image'], cooldown: 0 },
  ],
  go_standard: [
    { id: 'std-v1', name: 'Standard V1', ctx: '16K', out: '4K', caps: ['reasoning'], cooldown: 0 },
    { id: 'std-nocaps', name: 'Standard No Caps', ctx: '8K', out: '2K', caps: [], cooldown: 0 },
  ],
  go_economy: [],
  free_ratelimited: [],
};

function setupDOM(withModelData = false): void {
  const trigger = document.createElement('div');
  trigger.id = 'model-select-trigger';
  document.body.appendChild(trigger);

  const current = document.createElement('span');
  current.id = 'model-select-current';
  trigger.appendChild(current);

  const dropdown = document.createElement('div');
  dropdown.id = 'model-select-dropdown';
  document.body.appendChild(dropdown);

  const hidden = document.createElement('select');
  hidden.id = 'model-select';
  hidden.style.display = 'none';
  // happy-dom ignores .value= when no matching <option> exists
  const modelIds = withModelData
    ? Object.values(SAMPLE_MODELS).flat().map(m => m.id)
    : [''];
  for (const id of modelIds) {
    const opt = document.createElement('option');
    opt.value = id;
    hidden.appendChild(opt);
  }
  document.body.appendChild(hidden);

  if (withModelData) {
    const script = document.createElement('script');
    script.id = 'model-data';
    script.type = 'application/json';
    script.textContent = JSON.stringify(SAMPLE_MODELS);
    document.body.appendChild(script);
  }
}

function cleanupDOM(): void {
  document.getElementById('model-select-trigger')?.remove();
  document.getElementById('model-select-dropdown')?.remove();
  document.getElementById('model-select')?.remove();
  document.getElementById('model-data')?.remove();
}

describe('ModelSelector', () => {
  afterEach(() => {
    cleanupDOM();
    localStorage.clear();
  });

  describe('DOM structure', () => {
    it('creates trigger, current, and dropdown elements after init without model data', () => {
      setupDOM(false);
      const selector = new ModelSelector();
      selector.init();

      const trigger = document.getElementById('model-select-trigger');
      const current = document.getElementById('model-select-current');
      const dropdown = document.getElementById('model-select-dropdown');

      expect(trigger).not.toBeNull();
      expect(current).not.toBeNull();
      expect(dropdown).not.toBeNull();

      selector.dispose();
    });

    it('shows "No models available" in trigger when no model data is available', () => {
      setupDOM(false);
      const selector = new ModelSelector();
      selector.init();

      const current = document.getElementById('model-select-current');
      expect(current?.textContent).toBe('No models available');

      selector.dispose();
    });
  });

  describe('model rendering', () => {
    beforeEach(() => {
      setupDOM(true);
    });

    it('renders group labels for tiers that have models', () => {
      const selector = new ModelSelector();
      selector.init();

      const dropdown = document.getElementById('model-select-dropdown');
      const groups = dropdown?.querySelectorAll('.ms-group');
      expect(groups?.length).toBe(2);

      const labels = dropdown?.querySelectorAll('.ms-group-label');
      expect(labels?.length).toBe(2);
      expect(labels?.[0]?.textContent).toBe('GO Premium');
      expect(labels?.[1]?.textContent).toBe('GO Standard');

      selector.dispose();
    });

    it('renders model names', () => {
      const selector = new ModelSelector();
      selector.init();

      const dropdown = document.getElementById('model-select-dropdown');
      const items = dropdown?.querySelectorAll('.ms-item');
      const names = Array.from(items ?? []).map(el => el.querySelector('.ms-item-name')?.textContent);

      expect(names).toContain('Premium V1');
      expect(names).toContain('Premium V2');
      expect(names).toContain('Standard V1');
      expect(names).toContain('Standard No Caps');

      selector.dispose();
    });

    it('renders capability SVGs for models that have caps', () => {
      const selector = new ModelSelector();
      selector.init();

      const dropdown = document.getElementById('model-select-dropdown');

      const premiumV1 = dropdown?.querySelector('[data-model-id="premium-v1"]');
      expect(premiumV1?.querySelectorAll('.ms-cap-icon').length).toBe(2);

      const premiumV2 = dropdown?.querySelector('[data-model-id="premium-v2"]');
      expect(premiumV2?.querySelectorAll('.ms-cap-icon').length).toBe(3);

      const stdV1 = dropdown?.querySelector('[data-model-id="std-v1"]');
      expect(stdV1?.querySelectorAll('.ms-cap-icon').length).toBe(1);

      selector.dispose();
    });

    it('does not render capability SVGs for models without caps', () => {
      const selector = new ModelSelector();
      selector.init();

      const dropdown = document.getElementById('model-select-dropdown');
      const noCaps = dropdown?.querySelector('[data-model-id="std-nocaps"]');

      expect(noCaps?.querySelectorAll('.ms-cap-icon').length).toBe(0);

      selector.dispose();
    });
  });

  describe('selection', () => {
    beforeEach(() => {
      setupDOM(true);
    });

    it('updates current text when a model item is clicked', () => {
      const selector = new ModelSelector();
      selector.init();

      const dropdown = document.getElementById('model-select-dropdown');
      const premiumV2 = dropdown?.querySelector('[data-model-id="premium-v2"]') as HTMLElement;
      premiumV2?.click();

      const current = document.getElementById('model-select-current');
      expect(current?.textContent).toBe('Premium V2');

      selector.dispose();
    });

    it('updates hidden select value on selection', () => {
      const selector = new ModelSelector();
      selector.init();

      const hidden = document.getElementById('model-select') as HTMLSelectElement;
      const dropdown = document.getElementById('model-select-dropdown');
      const stdV1 = dropdown?.querySelector('[data-model-id="std-v1"]') as HTMLElement;
      stdV1?.click();

      expect(hidden?.value).toBe('std-v1');

      selector.dispose();
    });

    it('updates localStorage on selection', () => {
      const selector = new ModelSelector();
      selector.init();

      const dropdown = document.getElementById('model-select-dropdown');
      // premium-v1 is auto-selected, click a different model to trigger select()
      const stdV1 = dropdown?.querySelector('[data-model-id="std-v1"]') as HTMLElement;
      stdV1?.click();

      expect(localStorage.getItem('selected_model')).toBe('std-v1');

      selector.dispose();
    });
  });

  describe('edge cases', () => {
    it('does not crash when trigger element is missing', () => {
      const selector = new ModelSelector();
      expect(() => selector.init()).not.toThrow();
      selector.dispose();
    });
  });
});
