export class ReasoningState {
  constructor() {
    this._active = false;
  }

  enter() {
    var isNew = !this._active;
    this._active = true;
    return isNew;
  }

  exit() {
    this._active = false;
  }

  get isActive() {
    return this._active;
  }
}
