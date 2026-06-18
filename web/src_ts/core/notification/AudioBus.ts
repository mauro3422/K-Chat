import { IAudioBus } from '../../types/layout';
import { IEventBus } from '../../types/events';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

type SoundName = 'message' | 'error' | 'notification' | 'send' | 'connect';

const SOUND_FILES: Record<SoundName, string> = {
  message: '/static/sounds/message.mp3',
  error: '/static/sounds/error.mp3',
  notification: '/static/sounds/notification.mp3',
  send: '/static/sounds/send.mp3',
  connect: '/static/sounds/connect.mp3',
};

export class AudioBus implements IAudioBus {
  private logger: ILogger;
  private audioCache = new Map<string, HTMLAudioElement>();
  private brokenSounds = new Set<string>();
  private volume = 0.5;
  private muted = false;
  private eventBus?: IEventBus;
  private boundEvents: Array<{ event: string; cb: (...args: unknown[]) => void }> = [];

  constructor(eventBus?: IEventBus) {
    this.logger = getLogger('audio');
    this.eventBus = eventBus;
  }

  init(): void {
    if (!this.eventBus) return;
    const msgCb = () => this.play('message');
    const errCb = () => this.play('error');
    const notifCb = () => this.play('notification');
    const sendCb = () => this.play('send');

    this.eventBus.on('stream:content', msgCb);
    this.eventBus.on('stream:error', errCb);
    this.eventBus.on('notification:show', notifCb);
    this.eventBus.on('chat:send', sendCb);

    this.boundEvents.push(
      { event: 'stream:content', cb: msgCb as (...args: unknown[]) => void },
      { event: 'stream:error', cb: errCb as (...args: unknown[]) => void },
      { event: 'notification:show', cb: notifCb as (...args: unknown[]) => void },
      { event: 'chat:send', cb: sendCb as (...args: unknown[]) => void },
    );

    this.logger.info('init');
  }

  play(sound: SoundName): void {
    if (this.muted) return;
    if (this.brokenSounds.has(sound)) return; // Don't retry permanently broken files
    const src = SOUND_FILES[sound];
    if (!src) return;

    let audio = this.audioCache.get(sound);
    if (!audio) {
      if (typeof Audio === 'undefined') return;
      audio = new Audio(src);
      audio.volume = this.volume;
      audio.onerror = () => {
        this.audioCache.delete(sound);
        this.brokenSounds.add(sound); // Permanently mark as broken
      };
      this.audioCache.set(sound, audio);
    }
    audio.currentTime = 0;
    audio.play().catch(() => {
      this.brokenSounds.add(sound); // Play failed too → mark broken
    });
  }

  setVolume(vol: number): void {
    this.volume = Math.max(0, Math.min(1, vol));
    this.audioCache.forEach((a) => { a.volume = this.volume; });
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
  }

  destroy(): void {
    if (this.eventBus) {
      this.boundEvents.forEach(({ event, cb }) => this.eventBus!.off(event, cb as any));
    }
    this.boundEvents = [];
    this.audioCache.forEach((a) => { a.pause(); a.src = ''; });
    this.audioCache.clear();
    this.logger.info('destroy');
  }
}
