import { IEventBus } from '../types/events';
import { getLogger } from '../core/infra/LoggerFactory';
import { ILogger } from '../core/infra/Logger';

export interface ISkillsUI {
  init(): void;
}

interface Skill {
  name: string;
  title: string;
}

interface SkillDetail {
  name: string;
  content: string;
}

export class SkillsUI implements ISkillsUI {
  private eventBus: IEventBus;
  private fetchFn: typeof fetch;
  private renderMarkdown: (text: string) => string;
  private logger: ILogger = getLogger('skills');

  constructor(
    eventBus: IEventBus,
    renderMarkdown: (text: string) => string,
    fetchFn: typeof fetch,
  ) {
    this.eventBus = eventBus;
    this.renderMarkdown = renderMarkdown;
    this.fetchFn = fetchFn;
  }

  private dropdownEl: HTMLElement | null = null;
  private skillsListEl: HTMLElement | null = null;
  private toggleBtn: HTMLElement | null = null;
  private _clickCb: ((e: MouseEvent) => void) | null = null;

  init(): void {
    this.createModalContainer();
    this.createDropdown();
    this.attachEvents();
    this.fetchSkills();
    this.logger.info('init');
  }

  private createDropdown(): void {
    this.toggleBtn = document.getElementById('skills-toggle');
    if (!this.toggleBtn) return;

    this.dropdownEl = document.createElement('div');
    this.dropdownEl.id = 'skills-dropdown';
    this.dropdownEl.className = 'skills-dropdown';
    this.dropdownEl.innerHTML = `
      <div class="skills-dropdown-header">Skills</div>
      <div id="skills-dropdown-list" class="skills-dropdown-list"></div>
    `;
    this.skillsListEl = this.dropdownEl.querySelector('#skills-dropdown-list');
    this.toggleBtn.parentNode?.insertBefore(this.dropdownEl, this.toggleBtn.nextSibling);
  }

  private attachEvents(): void {
    this.toggleBtn?.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      this.toggleDropdown();
    });

    this._clickCb = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        this.dropdownEl &&
        !this.dropdownEl.contains(target) &&
        target !== this.toggleBtn &&
        !this.toggleBtn?.contains(target)
      ) {
        this.closeDropdown();
      }
    };
    document.addEventListener('click', this._clickCb);
  }

  private toggleDropdown(): void {
    if (!this.dropdownEl) return;
    const isOpen = this.dropdownEl.classList.toggle('open');
    if (isOpen) {
      this.logger.info('dropdown_open');
    }
  }

  private closeDropdown(): void {
    this.dropdownEl?.classList.remove('open');
  }

  private fetchSkills(): void {
    const listContainer = this.skillsListEl || document.getElementById('skills-dropdown-list');
    if (!listContainer) return;

    listContainer.textContent = 'Cargando...';

    this.fetchFn('/api/skills')
      .then(r => {
        if (!r.ok) throw new Error('Failed to load skills');
        return r.json() as Promise<Skill[]>;
      })
      .then(skills => {
        listContainer.textContent = '';
        this.logger.info('fetched_skills', `count=${skills.length}`);
        if (skills.length === 0) {
          listContainer.innerHTML = '<div class="skills-dropdown-empty">No hay skills</div>';
          return;
        }

        skills.forEach(skill => {
          const btn = document.createElement('button');
          btn.className = 'skills-dropdown-item';
          btn.dataset.name = skill.name;
          btn.textContent = `\u2022 ${skill.title}`;
          btn.addEventListener('click', () => {
            this.openSkill(skill.name);
            this.closeDropdown();
          });
          listContainer.appendChild(btn);
        });
      })
      .catch(err => {
        this.logger.error('fetch_skills_failed', String(err));
      });
  }

  dispose(): void {
    if (this._clickCb) document.removeEventListener('click', this._clickCb);
    this.dropdownEl?.remove();
  }

  private createModalContainer(): void {
    const oldModal = document.getElementById('skills-modal');
    if (oldModal) oldModal.remove();

    const modal = document.createElement('div');
    modal.id = 'skills-modal';
    modal.className = 'skills-modal';

    const content = document.createElement('div');
    content.className = 'skills-modal-content';

    const header = document.createElement('div');
    header.className = 'skills-modal-header';

    const title = document.createElement('h3');
    title.id = 'skills-modal-title';
    title.textContent = 'Instrucciones de Skill';
    header.appendChild(title);

    const closeBtn = document.createElement('button');
    closeBtn.className = 'skills-modal-close';
    closeBtn.innerHTML = '&times;';
    closeBtn.addEventListener('click', () => this.closeModal());
    header.appendChild(closeBtn);

    const body = document.createElement('div');
    body.id = 'skills-modal-body';
    body.className = 'skills-modal-body';

    content.appendChild(header);
    content.appendChild(body);
    modal.appendChild(content);

    modal.addEventListener('click', (e) => {
      if (e.target === modal) this.closeModal();
    });

    document.body.appendChild(modal);
  }

  openSkill(name: string): void {
    const modal = document.getElementById('skills-modal');
    const title = document.getElementById('skills-modal-title');
    const body = document.getElementById('skills-modal-body');
    if (!modal || !body) return;

    body.textContent = 'Cargando instrucciones...';
    modal.classList.add('show');
    this.logger.info('open_skill', `name=${name}`);

    this.fetchFn(`/api/skills/${name}`)
      .then(r => {
        if (!r.ok) throw new Error('Skill not found');
        return r.json() as Promise<SkillDetail>;
      })
      .then(data => {
        if (title) {
          title.textContent = `Skill: ${data.name.replace('-', ' ').toUpperCase()}`;
        }

        body.innerHTML = this.renderMarkdown(data.content);
        this.logger.info('skill_content_loaded', `name=${name} content_length=${data.content.length}`);
      })
      .catch(err => {
        this.logger.error('skill_load_failed', `name=${name} error=${err}`);
        body.textContent = 'Error al cargar las instrucciones de la skill.';
      });
  }

  private closeModal(): void {
    const modal = document.getElementById('skills-modal');
    if (modal) {
      modal.classList.remove('show');
      this.logger.info('close_modal');
    }
  }
}
