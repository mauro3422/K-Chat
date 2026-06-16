import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

export interface IFileUploader {
  readonly files: File[];
  init(): void;
  clear(): void;
  hasFiles(): boolean;
  getFiles(): File[];
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export class FileUploader implements IFileUploader {
  private _files: File[] = [];
  private blobUrls: string[] = [];
  private logger: ILogger = getLogger('file-upload');

  get files(): File[] {
    return this._files;
  }

  private addFile(file: File): void {
    if (file.size > MAX_FILE_SIZE) {
      this.logger.warn('size_exceeded', `name=${file.name} size=${file.size}`);
      alert(`El archivo "${file.name}" excede el límite de 10MB.`);
      return;
    }
    const exists = this._files.some(
      (af) => af.name === file.name && af.size === file.size
    );
    if (!exists) {
      this._files.push(file);
      this.logger.info('file_added', `name=${file.name} size=${file.size} type=${file.type}`);
    }
  }

  init(): void {
    const input = document.getElementById('file-input') as HTMLInputElement;
    const btn = document.getElementById('attach-btn');
    if (btn && input) {
      btn.addEventListener('click', () => input.click());
      input.addEventListener('change', (e: Event) => {
        const target = e.target as HTMLInputElement;
        const fileList = target.files;
        if (fileList) {
          Array.from(fileList).forEach((f) => this.addFile(f));
        }
        this.renderPreview();
        target.value = '';
      });
    }

    const msgInput = document.getElementById('msg-input');
    if (msgInput) {
      msgInput.addEventListener('paste', (e: ClipboardEvent) => {
        const items = e.clipboardData?.items;
        if (!items) return;
        let hasImage = false;
        for (let i = 0; i < items.length; i++) {
          if (items[i].type.startsWith('image/')) {
            hasImage = true;
            break;
          }
        }
        if (!hasImage) return;
        this.logger.info('paste_with_image');

        e.preventDefault();
        const textContent = e.clipboardData.getData('text/plain');

        for (let i = 0; i < items.length; i++) {
          if (items[i].type.startsWith('image/')) {
            let file = items[i].getAsFile();
            if (!file) continue;
            const ext = file.type.split('/')[1] || 'png';
            const timestamp = Date.now();
            file = new File([file], `clipboard-${timestamp}.${ext}`, { type: file.type });
            this.addFile(file);
          }
        }

        this.renderPreview();

        if (textContent && textContent.trim()) {
          const inputEl = document.getElementById('msg-input') as HTMLTextAreaElement;
          if (inputEl) {
            const start = inputEl.selectionStart;
            const end = inputEl.selectionEnd;
            const before = inputEl.value.substring(0, start);
            const after = inputEl.value.substring(end);
            inputEl.value = before + textContent + after;
            inputEl.selectionStart = inputEl.selectionEnd = start + textContent.length;
            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
          }
        }
      });
    }

    const dropZone = document.querySelector('.chat-input-container') as HTMLElement;
    if (dropZone) {
      dropZone.addEventListener('dragenter', (e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('drag-over');
        this.logger.debug('drag_enter');
      });
      dropZone.addEventListener('dragover', (e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer) {
          e.dataTransfer.dropEffect = 'copy';
        }
      });
      dropZone.addEventListener('dragleave', (e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        const related = e.relatedTarget as Node | null;
        if (!related || !dropZone.contains(related)) {
          dropZone.classList.remove('drag-over');
          this.logger.debug('drag_leave');
        }
      });
      dropZone.addEventListener('drop', (e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('drag-over');
        this.logger.info('drop');

        const items = e.dataTransfer?.items || [];
        const dtFiles = e.dataTransfer?.files || [];
        let hasFiles = false;

        for (let i = 0; i < dtFiles.length; i++) {
          const file = dtFiles[i];
          if (file.size > 0 && !file.type.startsWith('text/uri-list')) {
            hasFiles = true;
            this.addFile(file);
          }
        }

        if (!hasFiles && items.length > 0) {
          for (let j = 0; j < items.length; j++) {
            if (items[j].kind === 'string' && items[j].type === 'text/uri-list') {
              items[j].getAsString((url: string) => {
                const inputEl = document.getElementById('msg-input') as HTMLTextAreaElement;
                if (inputEl && url) {
                  const start = inputEl.selectionStart;
                  const before = inputEl.value.substring(0, start);
                  const after = inputEl.value.substring(start);
                  inputEl.value = before + url + after;
                  inputEl.selectionStart = inputEl.selectionEnd = start + url.length;
                  inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                }
              });
              break;
            }
          }
        }

        if (hasFiles) {
          this.renderPreview();
        }
      });
    }
  }

  private renderPreview(): void {
    const container = document.getElementById('attach-preview');
    if (!container) return;

    this.blobUrls.forEach((url) => URL.revokeObjectURL(url));
    this.blobUrls = [];

    container.innerHTML = '';
    this._files.forEach((file, idx) => {
      const item = document.createElement('div');
      item.className = 'attach-item';

      if (file.type.startsWith('image/')) {
        const img = document.createElement('img');
        const url = URL.createObjectURL(file);
        this.blobUrls.push(url);
        img.src = url;
        item.appendChild(img);
      } else if (file.type === 'application/pdf') {
        const icon = document.createElement('span');
        icon.textContent = '\uD83D\uDCC4';
        icon.className = 'attach-icon';
        item.appendChild(icon);
      } else if (file.type.startsWith('audio/')) {
        const icon = document.createElement('span');
        icon.textContent = '\uD83C\uDFB5';
        icon.className = 'attach-icon';
        item.appendChild(icon);
      } else {
        const icon = document.createElement('span');
        icon.textContent = '\uD83D\uDCCE';
        icon.className = 'attach-icon';
        item.appendChild(icon);
      }

      const name = document.createElement('span');
      name.className = 'attach-name';
      name.textContent = file.name.length > 15 ? file.name.substring(0, 12) + '...' : file.name;
      item.appendChild(name);

      const remove = document.createElement('button');
      remove.className = 'attach-remove';
      remove.textContent = '\u00D7';
      remove.onclick = () => {
        const removed = this._files[idx];
        this._files.splice(idx, 1);
        this.renderPreview();
        if (removed) this.logger.info('file_removed', `name=${removed.name}`);
      };
      item.appendChild(remove);

      container.appendChild(item);
    });
  }

  clear(): void {
    this._files = [];
    this.blobUrls.forEach((url) => URL.revokeObjectURL(url));
    this.blobUrls = [];
    this.renderPreview();
  }

  hasFiles(): boolean {
    return this._files.length > 0;
  }

  getFiles(): File[] {
    return this._files;
  }
}
