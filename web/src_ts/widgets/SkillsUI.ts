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

  init(): void {
    this.fetchSkills();
    this.createModalContainer();
    this.logger.info('init');
  }

  private fetchSkills(): void {
    const listContainer = document.getElementById('skills-sidebar-list');
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
          listContainer.innerHTML = '<span class="session-empty">No hay skills</span>';
          return;
        }

        skills.forEach(skill => {
          const btn = document.createElement('button');
          btn.className = 'skill-item-btn';
          btn.dataset.name = skill.name;
          btn.textContent = `\u2022 ${skill.title}`;
          btn.addEventListener('click', () => {
            this.openSkill(skill.name);
          });
          listContainer.appendChild(btn);
        });
      })
      .catch(err => {
        this.logger.error('fetch_skills_failed', String(err));
      });
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
