# Design System Document: Industrial Precision & Clarity

## 1. Overview & Creative North Star

### The Creative North Star: "The Technical Curator"
Industrial environments are chaotic; the interface should be the antidote. This design system moves away from the cluttered "dashboard fatigue" of traditional plant software and toward a **Technical Curator** aesthetic. It balances the utilitarian necessity of a high-visibility safety tool with the sophisticated spatial awareness of an editorial layout.

By utilizing intentional asymmetry, deep tonal layering, and "Safety Orange" (#F28C00) as a surgical strike of color, we create an environment that commands attention without causing fatigue. We prioritize cognitive ease through high-contrast typography scales and physical depth, ensuring that on a high-traffic plant floor, the most critical data point is always the most visible.

---

## 2. Colors

This palette is designed to function under varied lighting conditions, from dim control rooms to bright factory floors.

### Tonal Foundation
*   **Surface & Backgrounds:** The system relies on a "Cool Grey" foundation (`surface`: #F9F9F9) to reduce eye strain compared to pure white.
*   **Primary Accent:** `primary_container` (#F28C00) is our "Safety Orange." It is reserved strictly for interactive elements and critical status alerts.
*   **Tertiary Accents:** `tertiary` (#006495) provides a professional, calm counterpoint for non-critical data visualization.

### The "No-Line" Rule
To achieve a premium, custom feel, **1px solid borders are prohibited for sectioning.** Boundaries must be defined through background color shifts. Use `surface_container_low` sections sitting on a `surface` background to create structural separation. This mimics the appearance of machined parts and creates a cleaner, more modern visual field.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers.
*   **Level 0 (Base):** `surface` (#F9F9F9)
*   **Level 1 (Sections):** `surface_container_low` (#F3F3F3)
*   **Level 2 (Cards/Interaction):** `surface_container_lowest` (#FFFFFF)

### The "Glass & Gradient" Rule
For floating overlays (like the inspection modals seen in reference), use semi-transparent surface colors with a `backdrop-blur` of 12px. CTAs should utilize a subtle vertical gradient from `primary` (#8D4F00) to `primary_container` (#F28C00) to give buttons a "tactile" 3D quality that feels high-end and intentional.

---

## 3. Typography

The typography strategy pairs **Manrope** (Display/Headlines) with **Inter** (Functional Body/Labels).

*   **Display & Headlines (Manrope):** Chosen for its geometric precision and modern technical feel. Large `display-lg` (3.5rem) should be used for critical real-time metrics (e.g., "Pallet 12").
*   **Titles & Body (Inter):** A workhorse typeface for legibility. `title-md` (1.125rem) is used for list items and card headers to ensure readability at a distance.
*   **Label Scale:** `label-sm` (0.6875rem) is used for secondary data like "St155 — Sch1," providing a clear hierarchy that doesn't compete with primary actions.

The contrast between the bold, expansive Manrope and the compact, functional Inter signals to the user: "Look here for status, read here for detail."

---

## 4. Elevation & Depth

### The Layering Principle
Depth is achieved by "stacking" tonal tiers. Place a `surface_container_lowest` card on a `surface_container_low` background. This creates a soft, natural lift that communicates hierarchy without the visual noise of dark lines.

### Ambient Shadows
When an element must "float" (e.g., high-priority alert badges or primary modals), use the following shadow specification:
*   **Blur:** 24px - 40px
*   **Opacity:** 6% - 10%
*   **Color:** A tinted version of `on_surface` (#1A1C1C).
This creates a sophisticated "ambient" light effect rather than a heavy, dated drop shadow.

### The "Ghost Border" Fallback
If a border is required for accessibility in low-contrast environments, use a **Ghost Border**: `outline_variant` at 15% opacity. Never use 100% opaque borders.

---

## 5. Components

### Buttons
*   **Primary:** Safety Orange (`primary_container`) with `on_primary_container` text. Use `rounded-md` (0.375rem) for a technical, precise feel.
*   **Secondary:** `surface_container_highest` background with `primary` text. No border.
*   **Action Icon:** Small buttons (e.g., "History" or "Change Pallet") should use `surface_container_high` with a ghost border and `label-md` typography.

### Industrial Status Badges (High-Contrast)
Badges must use the `full` roundedness scale. 
*   **Critical:** `primary_container` background / `on_primary_fixed` text.
*   **Stable:** `tertiary_container` background / `on_tertiary_container` text.
*   **Inactive:** `surface_dim` background / `on_surface_variant` text.

### Cards & Lists
**Forbid divider lines.** Separate list items using `surface_container_lowest` for the active item and `surface_container_low` for inactive items. Use the spacing scale (1rem - 1.5rem) to create clear vertical "lanes" of information.

### Inspection Annotations
Floating labels (as seen in the reference images) must use `surface_container_lowest` with a `lg` (0.5rem) corner radius. Pair these with a small black "index box" (e.g., `on_surface` background) to anchor the ID number, creating a clear visual anchor on technical drawings or photos.

---

## 6. Do's and Don'ts

### Do
*   **DO** use whitespace as a functional tool. Increase padding in high-stress areas of the app to prevent mis-taps.
*   **DO** use the `primary_container` (#F28C00) sparingly. If everything is orange, nothing is urgent.
*   **DO** ensure all touch targets for plant floor use are at least 44px in height.

### Don't
*   **DON'T** use black (#000000) for text. Use `on_surface` (#1A1C1C) to maintain a premium tonal range.
*   **DON'T** use 1px solid borders to separate list items. Use background-color shifts or 12px vertical gaps.
*   **DON'T** mix roundedness. If using `md` (0.375rem) for buttons, ensure all input fields and small cards follow the same radius to maintain "machined" consistency.