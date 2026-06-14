var attachedFiles = [];

var MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

function init() {
  var btn = document.getElementById('attach-btn');
  var input = document.getElementById('file-input');
  if (btn && input) {
    btn.addEventListener('click', function() { input.click(); });
    input.addEventListener('change', handleFileSelect);
  }
}

function handleFileSelect(e) {
  var files = Array.from(e.target.files);
  files.forEach(function(f) {
    if (f.size > MAX_FILE_SIZE) {
      alert('El archivo "' + f.name + '" excede el límite de 10MB.');
      return;
    }
    if (!attachedFiles.find(function(af) { return af.name === f.name && af.size === f.size; })) {
      attachedFiles.push(f);
    }
  });
  renderPreview();
  e.target.value = '';
}

function renderPreview() {
  var container = document.getElementById('attach-preview');
  if (!container) return;
  container.innerHTML = '';
  attachedFiles.forEach(function(file, idx) {
    var item = document.createElement('div');
    item.className = 'attach-item';

    if (file.type.startsWith('image/')) {
      var img = document.createElement('img');
      img.src = URL.createObjectURL(file);
      item.appendChild(img);
    } else if (file.type === 'application/pdf') {
      var icon = document.createElement('span');
      icon.textContent = '\uD83D\uDCC4';
      icon.className = 'attach-icon';
      item.appendChild(icon);
    } else if (file.type.startsWith('audio/')) {
      var icon = document.createElement('span');
      icon.textContent = '\uD83C\uDFB5';
      icon.className = 'attach-icon';
      item.appendChild(icon);
    } else {
      var icon = document.createElement('span');
      icon.textContent = '\uD83D\uDCCE';
      icon.className = 'attach-icon';
      item.appendChild(icon);
    }

    var name = document.createElement('span');
    name.className = 'attach-name';
    name.textContent = file.name.length > 15 ? file.name.substring(0, 12) + '...' : file.name;
    item.appendChild(name);

    var remove = document.createElement('button');
    remove.className = 'attach-remove';
    remove.textContent = '\u00D7';
    remove.onclick = function() { attachedFiles.splice(idx, 1); renderPreview(); };
    item.appendChild(remove);

    container.appendChild(item);
  });
}

function getFiles() { return attachedFiles; }
function clear() { attachedFiles = []; renderPreview(); }
function hasFiles() { return attachedFiles.length > 0; }

export const FileAttachment = { init: init, getFiles: getFiles, clear: clear, hasFiles: hasFiles };
