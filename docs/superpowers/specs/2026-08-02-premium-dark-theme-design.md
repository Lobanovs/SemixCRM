# Premium Dark Theme Design

## Goal

Turn the existing blue-gray night mode into a coherent premium black desktop theme while preserving the current light theme, navigation, data, and theme persistence behavior.

## Chosen direction

Use **Graphite Black + Electric Blue**:

- app canvas: near-black `#06080b` instead of flat pure black;
- sidebar and top bar: `#080a0e` with subtle separation from the canvas;
- primary surfaces: `#0d1015`;
- elevated and interactive surfaces: `#121720` and `#171d27`;
- borders: translucent white at 8-14% opacity;
- primary text: `#f7f9fc`;
- secondary text: `#a0a9b8`;
- brand and focus accent: `#4c8dff` / `#75a7ff`;
- status colors remain semantic and are adjusted only for dark-theme contrast.

This direction keeps the existing Semix blue identity. Pure OLED black was rejected because it makes the interface visually flat and creates harsh contrast. Black with gold was rejected because it would change the product brand and collide with warning/status colors.

## Visual system

### Depth

Depth comes from three restrained tools:

1. tonal separation between canvas, panels, and elevated controls;
2. thin low-opacity borders;
3. soft shadows and a very subtle blue glow on active or focused elements only.

Cards must not use heavy gradients or permanent neon glows. Hover states lift the border and surface slightly within 160-220 ms.

### Navigation

The active sidebar item uses a dark blue-tinted surface, a brighter blue icon/text, and an inset accent line. Inactive items stay muted, and hover does not become brighter than the active state.

### Typography and accessibility

- Primary copy uses near-white, not absolute white.
- Secondary copy remains at least `#a0a9b8` on the chosen surfaces.
- Focus rings are visible on keyboard navigation.
- Native controls opt into `color-scheme: dark`.
- Motion respects `prefers-reduced-motion`.

### Coverage

The premium tokens and overrides cover:

- shell, sidebar, top bar, and dashboard;
- all data pages, rows, cards, tables, filters, and form controls;
- schedule/calendar surfaces;
- parser/history/archive panels and modals;
- AI client-message workspace;
- AI settings;
- Useful Things catalog and its dialogs;
- feedback, warning, success, and destructive states.

## Implementation boundary

Add a dedicated `src/premium-dark.css` loaded after the existing styles. This keeps the large legacy stylesheet stable, gives the new theme one source of truth, and ensures page-specific CSS cannot reintroduce the old slate palette. Add `data-theme="premium-dark"` to the app shell only while dark mode is active so the visual contract is explicit and testable.

No component layout, copy, API behavior, backend code, or light-theme colors are changed.

## Verification

- A frontend test proves the dark toggle applies the premium theme marker and still persists `semix-crm-theme=dark`.
- The complete frontend test suite and production build pass.
- Browser checks verify computed colors and visual hierarchy on the dashboard, Settings, Useful Things, Clients, and at least one modal.
- Browser console is checked for errors after the changes.
