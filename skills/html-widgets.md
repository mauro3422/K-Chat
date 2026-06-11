# Skill: Interactive HTML Widgets

Allows the agent to generate interactive visual interfaces (like calculators, planners, charts, or simple games) directly in the chat conversation.

## Output Format
To generate a widget, write a Markdown code block using the `html-widget` language tag.

* **Temporary Widgets (Draft)**: Use the simple block tag `html-widget`. It will be treated as a draft and will not enable version controls or editing. Note: The manual save button has been removed from the UI; use the `save_widget` action when you consider it appropriate to consolidate and promote a widget.
* **Official Widgets (Versioned)**: Append the unique widget name in lowercase with no spaces next to the language tag, e.g.: `html-widget calculator` or `html-widget notes`. This immediately enables versioning, in-situ editing, and change history in the interface (allowing the user to edit and save new versions manually).
* **Invoking/Loading Saved Widgets**: If the widget has already been officially saved in the system (you know this from your memory or by using `get_widget_code`), **NEVER** print its full source code in your chat response again. Instead, simply write the inline tag `[Widget: widget-name]` in your text (e.g., `Here's the widget: [Widget: quick-notes]`). The system will detect this call in real-time during streaming, asynchronously retrieve the code from the global database, and render the widget instantly without flooding the chat with repetitive code or inducing syntax errors.

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
