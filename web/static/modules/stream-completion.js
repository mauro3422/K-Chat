export function handleSuccessfulStream(params) {
  var retryController = params.retryController;
  var refreshSidebar = params.refreshSidebar;
  var debugPanel = params.debugPanel;

  if (retryController && typeof retryController.resetRetryCount === 'function') {
    retryController.resetRetryCount();
  }

  if (typeof refreshSidebar === 'function') {
    refreshSidebar();
  }

  if (debugPanel && debugPanel.debugVisible && typeof debugPanel.refreshDebug === 'function') {
    debugPanel.refreshDebug();
  }
}
