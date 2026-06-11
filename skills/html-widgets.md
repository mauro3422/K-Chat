# Skill: Interactive HTML Widgets

Allows the agent to generate interactive visual interfaces (like calculators, planners, charts, or simple games) directly in the chat conversation.

## Output Format
* **Temporary Widgets (Draft)**: Use the Markdown code block `` ```html-widget ```` to render directly in the chat. Keep the HTML compact (< 500 chars) to avoid the loop detector. Example:
  ```html-widget
  <div style="padding:16px;background:#161b22;border-radius:8px;color:#c9d1d9">
    <h3>Hello</h3>
    <p>Temp widget</p>
  </div>
  ```
* **Official Widgets (Versioned)**: When the user confirms they want to persist it, call `save_widget(widget_id, code)` to save, then invoke with `[Widget: widget_id]`.
* **Invoking Saved Widgets**: Use `[Widget: widget-name]` inline — the system retrieves and renders it.

All content in this block must be self-contained HTML, CSS, and JavaScript code. Do not add text explanations inside the code block.

Block example:
```html-widget
<div id="app">
  <!-- Your HTML structure here -->
</div>
<style>
  /* Your CSS styles here */
</style>
<script>
  // Your JavaScript logic here
</script>
```

## State Persistence
Widgets can persist their state so it is not lost when the user reloads the page (F5) or navigates through session history.

To use persistence:
1. **Load Initial State**: On startup, the widget can read `window.initialState` (which will contain the last saved state as a JavaScript object, or `null`/`undefined` if it is the first execution).
2. **Save New State**: Whenever the user interacts and changes the state (e.g., a button click, a modified text field), call the function exposed in the iframe:
   `window.saveState(stateObject)` (which transparently persists to the SQLite database in the background).

### Example Structure with Persistence:
```html-widget
<div id="app" style="text-align: center;">
  <h3>Persistent Counter</h3>
  <div id="counter" style="font-size: 2rem; margin: 10px 0; color: #fff;">0</div>
  <button id="btn" style="padding: 8px 16px; border-radius: 8px; cursor: pointer;">Increment</button>
</div>
<script>
  // 1. Load persisted initial state (if exists) or initialize default
  const state = window.initialState || { clickCount: 0 };

  // 2. Use the data to initialize the UI
  const counter = document.getElementById('counter');
  const btn = document.getElementById('btn');
  counter.textContent = state.clickCount;

  btn.onclick = () => {
    state.clickCount++;
    counter.textContent = state.clickCount;
    // 3. Persist the new state
    window.saveState(state);
  };
</script>
```

## Design Guidelines
- Use modern dark styles (fluid HSL colors, subtle borders, clean fonts like system-ui).
- Do not use `height: 100vh;` or `width: 100vw;` on `html` or `body` tags, since widgets run inside a dynamically-sized iFrame. Use fluid containers that adapt to their content.
- Add micro-interactions (`:hover` and `:active` effects on buttons and cards).

## Size Limits (Mandatory)
The widget iframe grows automatically with its content. To keep the UI clean:

- **Recommended maximum**: 600px height. If your widget exceeds this, split it into collapsible sections or use tabs.
- **Minimum**: 60px height. Do not create widgets smaller than this.
- **Width**: Always `width: 100%` of the container. Do not use fixed widths in px.
- **No scrolling**: The widget must NOT have internal scroll. If the content is long, use accordions, tabs, or collapsible sections instead of scroll.
- **No fixed height**: Do not use `height: Xpx` on the body or main container. Let the content define its height naturally.
