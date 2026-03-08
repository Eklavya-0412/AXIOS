The "Google AI Studio" Master Design Recipe
1. Color Palette (Strict Dark Mode)
Main App Background: #131314 (Very dark, almost black)
Card / Surface Background: #1E1F20 (Slightly lighter dark gray for panels, sidebars, and containers)
Primary Text: #E3E3E3 (Clean off-white)
Secondary Text / Labels / Axes: #C4C7C5 (Muted light gray)
Borders & Dividers: #444746 (Subtle dark gray—used for separating sections and card outlines)
Primary Accent / Active: #A8C7FA (Soft Google Blue - use for active tabs, primary buttons, or main chart lines)
Secondary Accent (Optional): #8AB4F8 (Slightly deeper blue)
Success Indicator: #81C995 (Muted green)
Warning Indicator: #FDE293 (Muted yellow)
Critical / Error Indicator: #F28B82 (Muted red/coral)
2. Typography
Font Family: Inter, Roboto, Google Sans, or system sans-serif.
Headers: Keep them small and understated. Use font weights like Medium (500) or Semi-bold (600). Absolutely no giant, bold headers.
Body/Metrics: 13px - 14px size.
Text Effects: ZERO text-shadows. ZERO glows.
3. Component Styling Rules
Cards & Containers: Background #1E1F20, border 1px solid #444746, border-radius 8px to 12px. NO BOX SHADOWS. NO GLOWS.
Buttons: Flat and minimal.
Default buttons: Background #131314, border 1px solid #444746, text #A8C7FA or #E3E3E3. Border-radius 20px (pill shape) or 8px (standard).
Primary action buttons: Background #A8C7FA (with dark text #000000) or subtle dark gray with #A8C7FA text.
Hover effects: Subtle brightness shift or background tint only. No scaling, no neon borders.
Status Badges / Tags (for anomalies like bgp_down, congested): * Instead of glowing red blocks, use a very subtle dark red background (e.g., rgba(242, 139, 130, 0.1)) with a 1px solid rgba(242, 139, 130, 0.3) border, and #F28B82 text. Border radius 4px.
Status Indicators: Use simple, solid 6px-8px circles (dots). Green for healthy, red for error. No glowing halos around them.
4. Data Visualization & Charts (Plotly / Streamlit)
Chart Backgrounds: Transparent (rgba(0,0,0,0)).
Gridlines: Horizontal only, 1px solid #444746 or lighter (rgba(255,255,255,0.05)). No vertical gridlines.
Line Charts (Telemetry): Line width 2px. Smooth or straight lines are fine. Use the Primary Blue (#A8C7FA) for main metrics, Success Green (#81C995) for success rates/health. Absolutely no area fill gradients beneath the lines unless at 5% opacity.
Bar Charts (API Usage/Errors): Flat solid fill (no gradients, no borders). Use primary blue.
Progress Bars / Rate Limits: Flat, 4px height lines. Yellow (#FDE293) for warnings, Red (#F28B82) for limits reached.
Legends & Axes: Text color #C4C7C5, font size 11px-12px.
Topology Graph (streamlit-agraph): Refactor the node styles. Nodes should be flat circles (no 3D effects). Edges should be thin, straight lines (#444746). Highlighted/backup routes should be a simple solid blue or green line.