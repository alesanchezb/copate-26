# Design System Document: Industrial Precision Interface

## 1. Overview & Creative North Star
**Creative North Star: "The Kinetic Observatory"**

In high-stakes industrial environments like welding cells, the interface must be more than a dashboard—it must be an authoritative, living extension of the machinery itself. This design system rejects the "flat web" aesthetic in favor of a high-end, editorial approach to industrial monitoring. 

By leveraging **intentional asymmetry**, we direct the eye toward anomalies rather than burying them in a rigid grid. The layout utilizes a "HUD-first" (Heads-Up Display) philosophy, where critical station data floats on a base of deep obsidian textures. We move away from generic templates by using dramatic typography scales and tonal layering to create a sense of depth, reliability, and technical sophistication.

---

## 2. Colors: Tonal Depth & The "No-Line" Rule
The color palette is engineered for high-contrast legibility in low-light factory environments. It utilizes a Deep Blue foundation with surgical applications of semantic color.

### The Palette
- **Core Surfaces:** `background` (#131313) is the canvas. Use `surface_container_lowest` (#0e0e0e) for recessed log areas and `surface_container_high` (#2a2a2a) for active station cards.
- **The Blue Engine:** `primary` (#a5c8ff) is used sparingly for active data points. Main UI accents utilize `primary_container` (#004c8f) to maintain a low visual vibration.
- **Semantic Precision:** 
    - **Good (Emerald):** Use `tertiary` (#70d8c8) for normal operations.
    - **Warning (Amber):** Use `secondary_fixed` (#cfe6f2) but shift to custom Amber Orange for warnings.
    - **Alert (Ruby):** Use `error` (#ffb4ab) on `error_container` (#93000a).

### Strategic Implementation
- **The "No-Line" Rule:** Prohibit the use of 1px solid borders to section the HUD or the log sidebar. Boundaries must be defined solely through background shifts (e.g., the sidebar log in `surface_container_low` sitting against the `surface` main stage).
- **Surface Nesting:** Treat the UI as a physical stack. The station cards (HUD) should feel like they are floating above the logs through a shift from `surface_container` to `surface_bright`.
- **Glass & Gradient:** For floating alerts or modal overlays, use **Glassmorphism**. Apply a backdrop-blur (12px-20px) to semi-transparent versions of `surface_variant`. 
- **Signature Texture:** Apply a subtle linear gradient from `primary_container` to `surface_container_lowest` for the background of the active station to give it a "technical glow."

---

## 3. Typography: Data Authority
The typography system uses a dual-font strategy to balance industrial character with technical clarity.

- **Display & Headlines (Space Grotesk):** This typeface provides a futuristic, precision-engineered feel. Use `display-lg` and `headline-lg` for large-scale telemetry values (e.g., "STATION 01" or "TEMP: 1450°C"). Its wide stance conveys stability.
- **Body & Labels (Inter):** Inter is used for high-density data tables and real-time logs. It is chosen for its exceptional legibility at small sizes (`label-sm` at 11px) and its neutral, "non-designed" look that prioritizes information over style.
- **Hierarchy of Urgency:** Use `headline-sm` in `error` color for critical failures. Use `label-md` with `on_surface_variant` for metadata in the log tables to reduce visual noise.

---

## 4. Elevation & Depth: Tonal Layering
We do not use structural lines to separate the station HUD from the time-series charts. We use the **Layering Principle**.

- **Ambient Shadows:** When a station card requires a "lift" to indicate it is selected, use an extra-diffused shadow: `box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4)`. The shadow should not be black; it should be a deep tint of the `primary_fixed_dim` color at 5% opacity.
- **The "Ghost Border" Fallback:** If high-glare environments require more definition, use a "Ghost Border": `outline-variant` (#434652) at 15% opacity. Never use 100% opaque borders.
- **Log Recessions:** The bottom or sidebar log area should feel "etched" into the interface. Accomplish this by using `surface_container_lowest` (#0e0e0e), creating a natural visual "sink" for historical data.

---

## 5. Components

### Station Cards (HUD)
- **Structure:** Use `roundedness-lg` (0.5rem). No borders.
- **State Styling:** Normal cards use `surface_container`. The active/focused card uses a glassmorphism effect with a `primary` glow on the top edge (2px).
- **Status Indicators:** Use a large, 8px circular "Status Pulse" using `tertiary` (Good) or `error` (Alert) rather than coloring the whole card.

### Real-Time Log Tables
- **Forbid Dividers:** Do not use horizontal lines between log entries. Use vertical spacing (8px) and alternating `surface_container_low` and `surface_container_lowest` backgrounds for row "zebra striping."
- **Typography:** Log timestamps use `label-sm` in `outline`. Event descriptions use `body-md` in `on_surface`.

### Time-Series Charts
- **Grid Lines:** If lines are necessary, use `outline_variant` at 10% opacity.
- **Data Lines:** 2px stroke width. Use `tertiary` for successful weld paths and `error` for spikes that exceed thresholds.
- **Fill:** Use a subtle gradient fill under the line (Primary to Transparent) to give the data "weight."

### Buttons & Controls
- **Primary Action:** Use `primary` (#a5c8ff) with `on_primary` text. Shape: `md` (0.375rem).
- **Ghost Actions:** Use `outline` text with no background for secondary machine settings.

---

## 6. Do's and Don'ts

### Do
- **DO** use asymmetry. If a station is in "Error" state, allow its card to expand or "break" the HUD alignment slightly to draw immediate attention.
- **DO** prioritize "glanceability." A welder should be able to see the status from 10 feet away using the semantic color cues.
- **DO** use `surface_bright` for interactive hover states to create a "light-up" effect.

### Don't
- **DON'T** use pure white (#FFFFFF) for text. Always use `on_surface` (#e5e2e1) to prevent eye strain in dark factory settings.
- **DON'T** use standard 1px borders. If you feel the need for a line, increase the gap between elements instead.
- **DON'T** use bright blue for alerts. Blue is "system information"; Red/Amber are "action required."
- **DON'T** crowd the sidebar logs. Use the `body-sm` scale and generous leading to ensure data doesn't "bleed" together during high-speed logging.