const listeners = new Map();

export const StreamDispatcher = {
  on(event, callback) {
    if (!listeners.has(event)) listeners.set(event, []);
    listeners.get(event).push(callback);
  },
  emit(event, data) {
    const fns = listeners.get(event) || [];
    for (const fn of fns) fn(data);
  },
};

export default StreamDispatcher;
