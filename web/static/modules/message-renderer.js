function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function renderMessage(msg) {
  const role = msg.role;
  const content = msg.content || "";
  const reasoning = msg.reasoning || "";
  const ts = msg.ts;
  const phases = msg.phases;
  const matched_tools = msg.matched_tools || [];

  const label = role === "user" ? "Tu" : "Kairos";
  const parts = [];

  parts.push(`<div class="msg ${role}">`);
  parts.push(`<div class="msg-label">${label}</div>`);

  if (role === "assistant" && phases && phases.length > 0) {
    const toolsByTurn = {};
    matched_tools.forEach(t => {
      const turn = t.turn || 0;
      if (!toolsByTurn[turn]) {
        toolsByTurn[turn] = [];
      }
      toolsByTurn[turn].push({ name: t.tool_name, status: t.status });
    });

    const hasAnyPhaseContent = phases.some(p => p.content);

    phases.forEach((phase, idx) => {
      const rText = phase.reasoning || "";
      if (rText) {
        parts.push(
          `<details class="reasoning" open>`,
          `<summary>Razonamiento</summary>`,
          `<div class="rt">${escapeHtml(rText)}</div>`,
          `</details>`
        );
      }
      if (hasAnyPhaseContent) {
        const pContent = phase.content || "";
        if (pContent) {
          parts.push(`<div class="msg-body md-content">${escapeHtml(pContent)}</div>`);
        }
      }

      const turnTools = toolsByTurn[idx + 1] || [];
      if (turnTools.length > 0) {
        parts.push(`<div class="tool-calls">`);
        turnTools.forEach(t => {
          const icon = t.status === "ok" ? "&#10003;" : "&#10007;";
          parts.push(`<span class="tc-item ${t.status}">${icon} ${escapeHtml(t.name)}</span>`);
        });
        parts.push(`</div>`);
      }
    });

    if (!hasAnyPhaseContent) {
      parts.push(`<div class="msg-body md-content">${escapeHtml(content)}</div>`);
    }
  } else {
    if (reasoning) {
      parts.push(
        `<details class="reasoning" open>`,
        `<summary>Razonamiento</summary>`,
        `<div class="rt">${escapeHtml(reasoning)}</div>`,
        `</details>`
      );
    }

    const bodyCls = role === "assistant" ? "msg-body md-content" : "msg-body";
    parts.push(`<div class="${bodyCls}">${escapeHtml(content)}</div>`);

    if (role === "assistant" && matched_tools.length > 0) {
      parts.push(`<div class="tool-calls">`);
      matched_tools.forEach(t => {
        const icon = t.status === "ok" ? "&#10003;" : "&#10007;";
        parts.push(`<span class="tc-item ${t.status}">${icon} ${escapeHtml(t.tool_name)}</span>`);
      });
      parts.push(`</div>`);
    }
  }

  const tsStr = ts ? String(ts).slice(0, 16) : "";
  parts.push(`<div class="msg-ts">${tsStr}</div>`);
  parts.push(`</div>`);

  return parts.join("\n");
}

export function renderMessageList(messages, widget_states) {
  const parts = [];
  
  if (!messages || messages.length === 0) {
    parts.push(`<div class="empty-state">Send a message to start</div>`);
  } else {
    messages.forEach(msg => {
      parts.push(renderMessage(msg));
    });
  }

  return parts.join("\n");
}
