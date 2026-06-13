export function mergeTranscript(existing, incoming) {
  const currentTokens = tokenize(existing);
  const incomingTokens = tokenize(incoming);
  if (incomingTokens.length === 0) return existing;
  if (currentTokens.length === 0) return incomingTokens.join(' ');

  const maxOverlap = Math.min(currentTokens.length, incomingTokens.length, 20);
  for (let overlap = maxOverlap; overlap > 0; overlap -= 1) {
    let matched = true;
    for (let i = 0; i < overlap; i += 1) {
      if (currentTokens[currentTokens.length - overlap + i] !== incomingTokens[i]) {
        matched = false;
        break;
      }
    }
    if (matched) {
      const remainderTokens = incomingTokens.slice(overlap);
      const remainder = collapseAdjacentTokens(remainderTokens).join(' ');
      return remainder ? existing.trim() + ' ' + remainder : existing.trim();
    }
  }

  const existingText = existing.trim();
  const incomingText = collapseAdjacentTokens(incomingTokens).join(' ');
  return existingText ? existingText + ' ' + incomingText : incomingText;
}

export function punctuateTranscript(existingText, incomingText, durationMs, gapMs) {
  var text = (existingText || '').trim();
  if (!text) return text;
  if (/[.!?]$/.test(text)) return text;
  if (/^\d+(?:\s+\d+)*$/.test(incomingText || '')) return text;
  var longPause = gapMs >= 1200;
  var mediumPause = gapMs >= 700;
  if (durationMs >= 2200 || longPause) return text + '.';
  if (durationMs >= 1200 || mediumPause) return text + ',';
  return text;
}

export function tokenize(text) {
  if (!text) return [];
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
}

export function splitTokens(text) {
  if (!text) return [];
  return text.trim().split(/\s+/).filter(Boolean);
}

export function collapseAdjacentTokens(tokens) {
  if (!tokens || tokens.length === 0) return [];
  const out = [];
  let runCount = 0;
  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i];
    const prev = out[out.length - 1];
    if (!prev || prev !== token) {
      out.push(token);
      runCount = 1;
      continue;
    }
    runCount += 1;
    if (runCount <= 2) {
      out.push(token);
    }
  }
  return out;
}

