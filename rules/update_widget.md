# update_widget
**Updates the code of an existing official widget, saving it as a new version in the session database so it can be iterated on without losing its previous state.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `code` | string | Sí |  | The new complete self-contained HTML, CSS, and JavaScript code for the widget. |
| `description` | string | No |  | Brief description of the changes made in this version (e.g. 'Added back button', 'Bug fixes'). |
| `widget_id` | string | Sí |  | The identifier or unique key of the widget to update (e.g. 'calculator', 'blog'). |
