# Frontend design system

VehiNode uses a **live routebook** visual language. The interface is for a self-hosting
owner of one or a few connected vehicles who needs to answer three questions quickly:
where is the vehicle, what is it doing, and is the telemetry path healthy? It should
feel calm, precise and approachable rather than like an industrial control panel or a
generic fleet SaaS template.

## Visual grammar

- IBM Plex Sans carries interface copy and large values; IBM Plex Mono is reserved for
  identifiers, timestamps, units, metric names and coordinates.
- The application sits in a restrained floating canvas over a flat slate surround.
  Light mode uses paper-white and cool neutral surfaces. Dark mode uses layered
  green-black surfaces. Cobalt blue is the primary action, selection and route color;
  green communicates healthy live state. Vehicle colors are preserved as data.
- A clear sidebar and quiet top bar frame the workspace. Active navigation uses a
  route-like edge marker rather than a raised navigation card. Containers use fine
  borders, modest radii and almost no decorative shadow.
- The live dashboard leads with the selected vehicle, a continuous vehicle switcher,
  the real recent route and a telemetry ledger. The vehicle page is a searchable
  garage roster with one row per vehicle, not a mosaic of interchangeable KPI and
  vehicle cards.

The recorded route is the signature device. It is drawn from historical GPS samples
and carries the same cobalt through energy progress, chart series and selected state.
It always corresponds to real data; avoid decorative telemetry ticks, arbitrary KPI
cards and logistics concepts that do not exist in the product.

Vehicle displays consume canonical metrics through one propulsion-aware presentation
policy. Propulsion chooses sensible priorities, but reported signals decide what can be
shown: EV views prefer traction battery and charging, combustion views prefer fuel and
engine data, and hybrid views can combine both. Unknown and missing values remain neutral
instead of being coerced to an EV state or a false zero.

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
added without changing components. Light, Dark and Auto use semantic CSS variables;
components must not infer theme from hard-coded background colors. Keyboard focus is
always visible, controls retain text labels, layouts work at 320 px, and nonessential
animation stops when `prefers-reduced-motion` is enabled.

The frontend packages fonts into the Vite build. Production still serves static files
and does not need Node or a third-party font service.

## Browser verification

`cd frontend && npm run test:e2e` builds the SPA, migrates a disposable local SQLite
database, launches the real FastAPI app and worker, and runs Playwright in Chromium;
CI runs the same journey against PostgreSQL.
The core journey covers first-account setup, vehicle creation, tracker enrollment,
device/human authentication isolation, idempotent telemetry, live state, route
history, dashboard persistence, hook execution/state, responsive localization,
theme switching and automated axe checks. Install the browser once with
`npx playwright install chromium`; CI installs the headless browser and Linux
dependencies explicitly.
