import { ICanvasOverlay, DrawBlock } from '../types/layout';
import { getLogger } from '../core/infra/LoggerFactory';
import { ILogger } from '../core/infra/Logger';

interface Particle {
  x: number; y: number;
  vx: number; vy: number;
  size: number;
  color: string;
  life: number;
  maxLife: number;
}

interface Raindrop {
  x: number; y: number;
  speed: number;
  length: number;
  opacity: number;
}

interface Snowflake {
  x: number; y: number;
  vx: number; vy: number;
  size: number;
  opacity: number;
}

interface Firework {
  x: number; y: number;
  particles: Particle[];
  age: number;
}

type EffectType = 'rain' | 'particles' | 'snow' | 'fireworks' | 'none';

export class CanvasOverlay implements ICanvasOverlay {
  private _canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private logger: ILogger;
  private animFrameId: number | null = null;
  private currentEffect: EffectType = 'none';

  // Rain
  private raindrops: Raindrop[] = [];
  // Snow
  private snowflakes: Snowflake[] = [];
  // Particles
  private particles: Particle[] = [];
  // Fireworks
  private fireworks: Firework[] = [];
  private lastFireworkSpawn = 0;

  // Drawing mode
  private drawMode = false;
  private isDrawing = false;
  private startX = 0;
  private startY = 0;
  private drawBlocks: DrawBlock[] = [];
  private onDrawCallback: ((blocks: DrawBlock[]) => void) | null = null;

  private effectColor = '#58a6ff';
  private effectOpacity = 0.6;

  constructor() {
    this.logger = getLogger('fx-canvas');
  }

  get canvas(): HTMLCanvasElement | null {
    return this._canvas;
  }

  init(containerId: string = 'fx-canvas'): void {
    this._canvas = document.getElementById(containerId) as HTMLCanvasElement | null;
    if (!this._canvas) {
      this.logger.warn('init', `#${containerId} not found`);
      return;
    }
    this.ctx = this._canvas.getContext('2d');
    this.resize();
    window.addEventListener('resize', () => this.resize());
    this.logger.info('init');
  }

  resize(): void {
    if (!this._canvas) return;
    this._canvas.width = window.innerWidth;
    this._canvas.height = window.innerHeight;
  }

  startEffect(effect: EffectType): void {
    this.currentEffect = effect;
    this.stopEffect();

    switch (effect) {
      case 'rain':
        this.raindrops = Array.from({ length: 150 }, () => this.createRaindrop());
        break;
      case 'snow':
        this.snowflakes = Array.from({ length: 100 }, () => this.createSnowflake());
        break;
      case 'particles':
        this.particles = Array.from({ length: 50 }, () => this.createParticle());
        break;
      case 'fireworks':
        this.fireworks = [];
        this.lastFireworkSpawn = 0;
        break;
      case 'none':
        this.clear();
        return;
    }

    this.logger.info('startEffect', effect);
    this.startLoop();
  }

  stopEffect(): void {
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    this.raindrops = [];
    this.snowflakes = [];
    this.particles = [];
    this.fireworks = [];
  }

  setOpacity(opacity: number): void {
    this.effectOpacity = Math.max(0, Math.min(1, opacity));
  }

  setColor(color: string): void {
    this.effectColor = color;
  }

  // ── Drawing Mode ──

  startDrawMode(onDraw: (blocks: DrawBlock[]) => void): void {
    this.drawMode = true;
    this.onDrawCallback = onDraw;
    if (!this._canvas) return;
    this._canvas.classList.add('draw-mode');
    this._canvas.addEventListener('mousedown', this.onPointerDown);
    this._canvas.addEventListener('mousemove', this.onPointerMove);
    this._canvas.addEventListener('mouseup', this.onPointerUp);
    this.logger.info('drawMode', 'started');
  }

  stopDrawMode(): void {
    this.drawMode = false;
    this.isDrawing = false;
    if (!this._canvas) return;
    this._canvas.classList.remove('draw-mode');
    this._canvas.removeEventListener('mousedown', this.onPointerDown);
    this._canvas.removeEventListener('mousemove', this.onPointerMove);
    this._canvas.removeEventListener('mouseup', this.onPointerUp);
    this.logger.info('drawMode', 'stopped');
  }

  clear(): void {
    if (!this.ctx || !this._canvas) return;
    this.ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
    this.drawBlocks = [];
  }

  destroy(): void {
    this.stopEffect();
    this.stopDrawMode();
    this._canvas = null;
    this.ctx = null;
  }

  // ── Render Loop ──

  private startLoop(): void {
    const loop = () => {
      if (this.currentEffect === 'none') return;
      this.render();
      this.animFrameId = requestAnimationFrame(loop);
    };
    loop();
  }

  private render(): void {
    if (!this.ctx || !this._canvas) return;
    const ctx = this.ctx;
    const w = this._canvas.width;
    const h = this._canvas.height;

    ctx.clearRect(0, 0, w, h);
    ctx.globalAlpha = this.effectOpacity;

    switch (this.currentEffect) {
      case 'rain': this.renderRain(ctx, w, h); break;
      case 'snow': this.renderSnow(ctx, w, h); break;
      case 'particles': this.renderParticles(ctx, w, h); break;
      case 'fireworks': this.renderFireworks(ctx, w, h); break;
    }

    ctx.globalAlpha = 1;
  }

  // ── Rain ──

  private createRaindrop(): Raindrop {
    return {
      x: Math.random() * (this._canvas?.width || 1920),
      y: Math.random() * (this._canvas?.height || 1080),
      speed: 8 + Math.random() * 12,
      length: 15 + Math.random() * 20,
      opacity: 0.3 + Math.random() * 0.4,
    };
  }

  private renderRain(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    ctx.strokeStyle = this.effectColor;
    ctx.lineWidth = 1;

    for (let i = 0; i < this.raindrops.length; i++) {
      const r = this.raindrops[i];
      ctx.globalAlpha = r.opacity * this.effectOpacity;
      ctx.beginPath();
      ctx.moveTo(r.x, r.y);
      ctx.lineTo(r.x - 2, r.y + r.length);
      ctx.stroke();

      r.y += r.speed;
      r.x -= 1.5;

      if (r.y > h + 20) {
        r.y = -20;
        r.x = Math.random() * w;
      }
      if (r.x < -20) r.x = w + 20;
    }
  }

  // ── Snow ──

  private createSnowflake(): Snowflake {
    return {
      x: Math.random() * (this._canvas?.width || 1920),
      y: Math.random() * (this._canvas?.height || 1080),
      vx: -0.5 + Math.random() * 1,
      vy: 1 + Math.random() * 2,
      size: 2 + Math.random() * 4,
      opacity: 0.4 + Math.random() * 0.6,
    };
  }

  private renderSnow(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    for (let i = 0; i < this.snowflakes.length; i++) {
      const s = this.snowflakes[i];
      ctx.globalAlpha = s.opacity * this.effectOpacity;
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
      ctx.fill();

      s.x += s.vx;
      s.y += s.vy;
      s.vx += (Math.random() - 0.5) * 0.1;

      if (s.y > h + 10) {
        s.y = -10;
        s.x = Math.random() * w;
      }
      if (s.x < -10) s.x = w + 10;
      if (s.x > w + 10) s.x = -10;
    }
  }

  // ── Particles ──

  private createParticle(): Particle {
    const w = this._canvas?.width || 1920;
    const h = this._canvas?.height || 1080;
    return {
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 2,
      vy: (Math.random() - 0.5) * 2,
      size: 2 + Math.random() * 4,
      color: ['#58a6ff', '#3fb950', '#f0883e', '#f85149', '#a5d6ff'][Math.floor(Math.random() * 5)],
      life: 100 + Math.random() * 200,
      maxLife: 300,
    };
  }

  private renderParticles(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx;
      p.y += p.vy;
      p.life--;

      const alpha = (p.life / p.maxLife) * this.effectOpacity;
      ctx.globalAlpha = alpha;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();

      if (p.life <= 0) {
        this.particles[i] = this.createParticle();
      }
    }
  }

  // ── Fireworks ──

  private renderFireworks(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    const now = Date.now();

    if (now - this.lastFireworkSpawn > 800 + Math.random() * 400) {
      this.fireworks.push({
        x: 100 + Math.random() * (w - 200),
        y: 100 + Math.random() * (h * 0.4),
        particles: Array.from({ length: 40 }, () => ({
          x: 0, y: 0,
          vx: (Math.random() - 0.5) * 8,
          vy: (Math.random() - 0.5) * 8,
          size: 2 + Math.random() * 3,
          color: ['#58a6ff', '#3fb950', '#f0883e', '#f85149', '#ff7b72', '#a5d6ff', '#d2a8ff'][Math.floor(Math.random() * 7)],
          life: 40 + Math.random() * 40,
          maxLife: 80,
        })),
        age: 0,
      });
      this.lastFireworkSpawn = now;
    }

    for (let fi = this.fireworks.length - 1; fi >= 0; fi--) {
      const fw = this.fireworks[fi];
      fw.age++;

      for (let i = 0; i < fw.particles.length; i++) {
        const p = fw.particles[i];
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.05;
        p.life--;

        const alpha = (p.life / p.maxLife) * this.effectOpacity;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(fw.x + p.x, fw.y + p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
      }

      if (fw.age > 100) {
        this.fireworks.splice(fi, 1);
      }
    }
  }

  // ── Drawing Mode Event Handlers ──

  private onPointerDown = (e: MouseEvent): void => {
    if (!this.drawMode || !this._canvas) return;
    this.isDrawing = true;
    this.startX = e.offsetX;
    this.startY = e.offsetY;
  };

  private onPointerMove = (e: MouseEvent): void => {
    if (!this.isDrawing || !this.ctx || !this._canvas) return;
    const ctx = this.ctx;
    const x = this.startX;
    const y = this.startY;
    const w = e.offsetX - x;
    const h = e.offsetY - y;

    ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
    this.drawBlocks.forEach(b => {
      ctx.strokeStyle = b.color;
      ctx.lineWidth = 2;
      ctx.strokeRect(b.x, b.y, b.w, b.h);
      ctx.fillStyle = b.color + '20';
      ctx.fillRect(b.x, b.y, b.w, b.h);
    });

    ctx.strokeStyle = this.effectColor;
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
    ctx.fillStyle = this.effectColor + '15';
    ctx.fillRect(x, y, w, h);
  };

  private onPointerUp = (e: MouseEvent): void => {
    if (!this.isDrawing) return;
    this.isDrawing = false;

    const w = e.offsetX - this.startX;
    const h = e.offsetY - this.startY;
    if (Math.abs(w) < 10 && Math.abs(h) < 10) return;

    const block: DrawBlock = {
      x: Math.min(this.startX, e.offsetX),
      y: Math.min(this.startY, e.offsetY),
      w: Math.abs(w),
      h: Math.abs(h),
      color: this.effectColor,
      type: 'cell',
    };
    this.drawBlocks.push(block);
    this.onDrawCallback?.([...this.drawBlocks]);

    if (this.ctx && this._canvas) {
      this.ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
      this.drawBlocks.forEach(b => {
        this.ctx!.strokeStyle = b.color;
        this.ctx!.lineWidth = 2;
        this.ctx!.strokeRect(b.x, b.y, b.w, b.h);
        this.ctx!.fillStyle = b.color + '20';
        this.ctx!.fillRect(b.x, b.y, b.w, b.h);
      });
    }
  };
}
