export class MessageWindowing {
  private observer: IntersectionObserver
  private messageData: Map<string, unknown> = new Map()
  private messageElements: Map<string, HTMLElement> = new Map()
  private estimatedHeights: Map<string, number> = new Map()
  private liveMsgId: string | null = null
  private readonly DEFAULT_HEIGHT = 80
  // Effectively disabled — huge rootMargin keeps all messages "visible"
  // avoiding virtualize-out/restore cycles that cause duplicate renders.
  // Re-enable with a smaller value when windowing is stable.
  private readonly OVERS_CAN = 99999

  constructor() {
    this.observer = new IntersectionObserver(
      (entries) => this._onIntersection(entries),
      { rootMargin: `${this.OVERS_CAN}px 0px`, threshold: 0 },
    )
  }

  setLiveMsgId(id: string | null): void {
    this.liveMsgId = id
  }

  observeMessage(el: HTMLElement, data: unknown): void {
    const msgId = el.dataset.msgId
    if (!msgId) return

    this.messageData.set(msgId, data)
    this.messageElements.set(msgId, el)
    this.observer.observe(el)

    requestAnimationFrame(() => {
      if (el.offsetHeight > 0) {
        this.estimatedHeights.set(msgId, el.offsetHeight)
      }
    })
  }

  unobserveMessage(id: string): void {
    const el = this.messageElements.get(id)
    if (el) {
      this.observer.unobserve(el)
      this.messageElements.delete(id)
    }
    this.messageData.delete(id)
    this.estimatedHeights.delete(id)
  }

  clear(): void {
    this.observer.disconnect()
    this.messageData.clear()
    this.messageElements.clear()
    this.estimatedHeights.clear()
    this.liveMsgId = null
  }

  destroy(): void {
    this.clear()
  }

  private _onIntersection(entries: IntersectionObserverEntry[]): void {
    for (const entry of entries) {
      const el = entry.target as HTMLElement
      const msgId = el.dataset.msgId
      if (!msgId) continue
      if (msgId === this.liveMsgId) continue

      if (!entry.isIntersecting) {
        this._virtualizeOut(el, msgId)
      } else {
        this._virtualizeIn(el, msgId)
      }
    }
  }

  private _virtualizeOut(el: HTMLElement, msgId: string): void {
    if (el.dataset.virtualized === 'true') return

    const height = this.estimatedHeights.get(msgId) || this.DEFAULT_HEIGHT
    el.dataset.virtualized = 'true'
    el.dataset.virtualHeight = String(height)
    el.style.height = `${height}px`
    el.style.overflow = 'hidden'
    el.innerHTML = `<div style="visibility:hidden;pointer-events:none;">&nbsp;</div>`
  }

  private _virtualizeIn(el: HTMLElement, msgId: string): void {
    if (el.dataset.virtualized !== 'true') return

    const data = this.messageData.get(msgId)
    if (!data) return

    el.dataset.virtualized = 'false'
    el.style.height = ''
    el.style.overflow = ''

    el.dispatchEvent(
      new CustomEvent('msg:restore', {
        detail: { msgId, data },
        bubbles: true,
      }),
    )
  }
}
