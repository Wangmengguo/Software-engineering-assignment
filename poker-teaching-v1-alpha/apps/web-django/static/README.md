# Shared Static Assets

This directory contains shared static assets that can be reused across multiple pages.

## Theme Toggle Component

The theme toggle functionality has been extracted into reusable components:

### Files:
- `css/theme-toggle.css` - Theme toggle styles
- `js/theme-toggle.js` - Theme toggle JavaScript functionality
- `templates/ui/_theme_toggle.html` - Theme toggle button HTML template

### Usage:

1. **Include CSS in your HTML head:**
   ```html
   <link rel="stylesheet" href="/static/css/theme-toggle.css">
   ```

2. **Include the button in your template:**
   ```html
   {% include "ui/_theme_toggle.html" %}
   ```

3. **Include JavaScript before closing body tag:**
   ```html
   <script src="/static/js/theme-toggle.js"></script>
   ```

### Features:
- Automatic theme detection and persistence using localStorage
- Smooth transitions between themes
- Hover effects on the toggle button
- Works across all pages that include these components

### Example Implementation:
See `poker_teaching_replay.html` and `poker_teaching_game_ui_skeleton_htmx_tailwind.html` for complete examples.
