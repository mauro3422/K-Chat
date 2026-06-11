let _currentSessionId = null;
let _initialized = false;

export const SessionContext = {
  init(sid) {
    _currentSessionId = sid;
    _initialized = true;
  },

  getSessionId() {
    return _currentSessionId;
  },

  isInitialized() {
    return _initialized;
  },

  setSessionId(sid) {
    var prev = _currentSessionId;
    _currentSessionId = sid;
    return prev;
  },

  createSessionUrlBuilder() {
    var sid = _currentSessionId;
    return {
      widgetCode: function(key) { return '/sessions/' + sid + '/widgets/' + encodeURIComponent(key) + '/code'; },
      widgetState: function(key) { return '/sessions/' + sid + '/widgets/' + encodeURIComponent(key) + '/state'; },
      widgetSave: function(key) { return '/sessions/' + sid + '/widgets/' + encodeURIComponent(key) + '/save'; },
      widgetVersions: function(key) { return '/sessions/' + sid + '/widgets/' + encodeURIComponent(key) + '/versions'; },
      versionCode: function(key, v) { return '/sessions/' + sid + '/widgets/' + encodeURIComponent(key) + '/versions/' + v + '/code'; },
      debug: function() { return '/sessions/' + sid + '/debug'; },
      sidebar: function() { return '/sidebar?current=' + sid; },
      chat: function(model) { return '/chat/' + sid + '?model=' + encodeURIComponent(model); },
      messages: function() { return '/sessions/' + sid + '/messages'; },
    };
  },

  reset() {
    _currentSessionId = null;
    _initialized = false;
  }
};

window.SessionContext = SessionContext;
export default SessionContext;
