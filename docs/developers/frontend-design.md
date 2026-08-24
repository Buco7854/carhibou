# Frontend design system

VehiNode uses a **connected-car workspace** visual language. The interface is for a
self-hosting vehicle owner who needs to answer three questions quickly: where is the
vehicle, what is it doing, and is the telemetry path healthy? It should feel calm,
precise and approachable rather than like an industrial control panel.

## Visual grammar

- IBM Plex Sans carries interface copy and large values; IBM Plex Mono is reserved for
  identifiers, timestamps, units, metric names and coordinates.
- The application sits in a large rounded canvas above a slate-to-peach background.
  Light mode uses white cards and warm neutral surfaces. Dark mode uses layered
  near-black surfaces. Bright orange is the primary action, selection and route color;
  green communicates healthy live state, while blue and amber support secondary data.
- A clear sidebar and restrained top bar frame the workspace. Cards use consistent
  medium radii, fine borders and soft shadows; they should remain airy rather than
  glossy or glass-like.
- The live dashboard begins with a compact fleet overview, then gives most of the
  canvas to vehicle selection, position and current telemetry. The vehicle page uses a
  searchable card grid with one dominant vehicle illustration per card.

The orange telemetry line is the signature device. It may describe a route, battery
progress, chart series or selected state. It always corresponds to real data; avoid
decorative HUD marks and avoid inventing logistics concepts that do not exist in the
product.

## Interaction and accessibility

English and French catalogs remain structurally identical so more locales can be
added without changing components. Light, Dark and Auto use semantic CSS variables;
components must not infer theme from hard-coded background colors. Keyboard focus is
always visible, controls retain text labels, layouts work at 320 px, and nonessential
animation stops when `prefers-reduced-motion` is enabled.

The frontend packages fonts into the Vite build. Production still serves static files
and does not need Node or a third-party font service.
