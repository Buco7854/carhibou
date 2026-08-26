# Frontend design system

VehiNode uses a **live routebook** visual language. The interface is for a self-hosting
owner of one or a few connected vehicles who needs to answer three questions quickly:
where is the vehicle, what is it doing, and is the telemetry path healthy? It should
feel calm, precise and approachable rather than like an industrial control panel or a
generic fleet SaaS template.

## Visual grammar

- IBM Plex Sans carries interface copy and large values; IBM Plex Mono is reserved for
  identifiers, timestamps, units, metric names and coordinates.
- The application fills the browser viewport without an ornamental outer frame.
  Light mode uses paper-white and cool neutral surfaces. Dark mode uses layered
  green-black surfaces. Cobalt blue is the primary action, selection and route color;
  green communicates healthy live state. Vehicle colors are preserved as data.
- A clear sidebar and quiet top bar frame the workspace. Active navigation uses a
  route-like edge marker rather than a raised navigation card. Containers use fine
  borders, modest radii and almost no decorative shadow.
- The dashboard destination opens one useful premade overview and lets the owner add,
  rename, select and default more dashboards. The dashboard itself is the page; editing
  enables controls on that same canvas instead of navigating to or framing an editor.
  Page-level dashboard actions live in one conventional overflow menu. The premade
  overview composes the same selector, map, media, energy, telemetry, chart and health
  widgets available to owners; unpinned widgets share the selector's reactive vehicle.
  Its grid is draggable on larger screens and
  becomes a stable single-column stack on phones. The vehicle page is a searchable
  photographic garage whose cards keep the same media geometry with or without a photo.

The recorded route is the signature device. It is drawn from historical GPS samples
and carries the same cobalt through energy progress, chart series and selected state.
It always corresponds to real data; avoid decorative telemetry ticks, arbitrary KPI
cards and logistics concepts that do not exist in the product.

Vehicle displays consume canonical metrics directly. They do not ask for, infer or show
a propulsion classification. A battery level is preferred when `battery.soc` exists,
fuel level is used when `fuel.level` exists, and secondary readings are selected from
the other reported keys. Unknown and missing values remain neutral instead of becoming
a false zero.

The VehiNode mark is an original three-node route forming a `V`. It remains legible as
a favicon and uses a single solid accent rather than a decorative illustration. The
map keeps the open Leaflet/OpenStreetMap stack, with neutralized tiles, a route halo,
start/current markers, a metric scale and explicit loading, empty and tile-failure
states. Do not replace it with a proprietary map service as a design shortcut.

## Anti-template rules

- Do not open a page with a greeting or a four-card KPI strip.
- Do not wrap every metric in an icon badge and rounded card.
- Do not use tiny labels to imitate a static portfolio mockup; operational text remains
  readable at normal browser zoom.
- Supplied visual references establish finish and mood, not page geometry. Preserve
  VehiNode's own information hierarchy and never reproduce a reference composition.
- A card must represent a real grouping or interaction boundary. Otherwise use spacing,
  alignment and dividers.

## Interaction and accessibility

English and French catalogs remain structurally identical so more locales can be
added without changing components. The initial language follows the browser until the
owner makes an explicit choice. `AppSelect` is an application-owned accessible combobox
and listbox—not a skinned native select—so its menu, focus, borders and chevrons remain
consistent and its popover cannot be clipped by a panel. Creation flows use the shared
modal component instead of expanding forms into the current page. Profiles have a
dedicated list page, a vertically aligned create/edit modal and a separate signal modal.
Hooks use the same modal creation pattern and show an explicit empty state before the
first hook. Light, Dark and Auto use semantic CSS variables;
components must not infer theme from hard-coded background colors. Keyboard focus is
always visible, controls retain text labels, layouts work at 320 px, and nonessential
animation stops when `prefers-reduced-motion` is enabled.

The frontend packages fonts into the Vite build. Production still serves static files
and does not need Node or a third-party font service.

## Browser verification

`cd frontend && npm run test:e2e` builds the SPA, migrates a disposable local SQLite
database, launches the real FastAPI app and worker, and runs Playwright in Chromium;
CI runs the same journey against PostgreSQL.
The core journey covers first-account setup, vehicle creation, agent enrollment,
device/human authentication isolation, idempotent telemetry, live state, route
history, dashboard persistence, hook execution/state, responsive localization,
theme switching and automated axe checks. Install the browser once with
`npx playwright install chromium`; CI installs the headless browser and Linux
dependencies explicitly.
