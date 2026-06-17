#!/bin/bash
# Fix widget-2 infinite growth bug: replace SVG <animate> with CSS animation
DB="memory/kairos_memory.db"

# Get current code
CODE=$(sqlite3 "$DB" "SELECT code FROM saved_widgets WHERE widget_id='geckairos-v2' ORDER BY version DESC LIMIT 1;")

# Fix 1: Remove SVG <animate> element, add CSS animation instead
FIXED=$(echo "$CODE" | sed 's|<rect x="82" y="108" width="3.5" height="12" fill="#00ffff" opacity="0.85"><animate attributeName="opacity" values="0.85;0.05;0.85" dur="0.7s" repeatCount="indefinite"/></rect>|<rect class="cursor" x="82" y="108" width="3.5" height="12" fill="#00ffff" opacity="0.85"/>|')

# Fix 2: Add CSS animation + overflow hidden to head style
FIXED=$(echo "$FIXED" | sed 's|box-sizing:border-box|box-sizing:border-box;overflow:hidden|')
FIXED=$(echo "$FIXED" | sed 's|body{background:#060a06|@keyframes blink{0%,100%{opacity:0.85}50%{opacity:0.05}}.cursor{animation:blink 0.7s steps(2) infinite}body{background:#060a06|')

echo "$FIXED" > /tmp/geckairos_v2_fixed.svg
echo "OK - fix applied"
echo "Length: $(echo "$FIXED" | wc -c) chars"
