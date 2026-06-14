/**
 * K-Chat Skills UI
 * Handles catalog fetching, rendering the list, and showing skill instructions in a modal overlay.
 */
import { ApiClient } from './api-client.js';

interface Skill {
  name: string;
  title: string;
}

interface SkillDetail {
  name: string;
  content: string;
}

export const SkillsUI = {
  init(): void {
    this.fetchSkills();
    this.createModalContainer();
  },

  fetchSkills(): void {
    const listContainer = document.getElementById('skills-sidebar-list');
    if (!listContainer) return;

    listContainer.textContent = 'Cargando...';

    fetch('/api/skills')
      .then(r => {
        if (!r.ok) throw new Error('Failed to load skills');
        return r.json() as Promise<Skill[]>;
      })
      .then(skills => {
        listContainer.textContent = '';
        if (skills.length === 0) {
          listContainer.innerHTML = '<span class="session-empty">No hay skills</span>';
          return;
        }

        skills.forEach(skill => {
          const btn = document.createElement('button');
          btn.className = 'skill-item-btn';
          btn.dataset.name = skill.name;
          btn.textContent = `• ${skill.title}`;
          btn.addEventListener('click', () => {
            this.openSkill(skill.name);
          });
          listContainer.appendChild(btn);
        });
      })
      .catch(err => {
        console.error(err);
        listContainer.textContent = 'Error al cargar';
      });
  },

  createModalContainer(): void {
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
  },

  openSkill(name: string): void {
    const modal = document.getElementById('skills-modal');
    const title = document.getElementById('skills-modal-title');
    const body = document.getElementById('skills-modal-body');
    if (!modal || !body) return;

    body.textContent = 'Cargando instrucciones...';
    modal.classList.add('show');

    fetch(`/api/skills/${name}`)
      .then(r => {
        if (!r.ok) throw new Error('Skill not found');
        return r.json() as Promise<SkillDetail>;
      })
      .then(data => {
        if (title) {
          title.textContent = `Skill: ${data.name.replace('-', ' ').toUpperCase()}`;
        }
        
        let html = '';
        const w = window as any;
        if (typeof w.marked !== 'undefined') {
          html = w.marked.parse(data.content);
        } else {
          html = `<pre style="white-space: pre-wrap;">${data.content}</pre>`;
        }

        if (typeof w.DOMPurify !== 'undefined') {
          html = w.DOMPurify.sanitize(html);
        }

        body.innerHTML = html;
      })
      .catch(err => {
        console.error(err);
        body.textContent = 'Error al cargar las instrucciones de la skill.';
      });
  },

  closeModal(): void {
    const modal = document.getElementById('skills-modal');
    if (modal) {
      modal.classList.remove('show');
    }
  }
};
