# Frontend design system

VehiNode uses a **field instrument** visual language. The interface is for a
self-hosting vehicle owner who needs to answer three questions quickly: where is the
vehicle, what is it doing, and is the telemetry path healthy? It should not resemble a
generic fleet-management template.

## Visual grammar

- Barlow Condensed identifies vehicles, pages and instrument values.
- IBM Plex Sans carries interface copy; IBM Plex Mono carries times, units, metric
  names, coordinates and system state.
- Light mode uses chalk and mineral greys. Dark mode uses layered green-slate rather
  than pure black. Petrol teal is the primary control color, signal lime marks live
  state, and rust is reserved for warnings or vehicle metadata.
- Panels use ruled divisions and small corner radii. Discrete records may be cards,
  but the product does not wrap every label or number in a floating card.
- The live dashboard is vehicle-first: identity and selector, map, live instruments,
  then historical trace. Fleet summaries must not displace that primary task.

The telemetry signal rail is the signature device. It may represent connection
quality, battery cells, sample ticks, or time. Do not add decorative HUD marks that do
not correspond to real state.

## Interaction and accessibility

English and French catalogs remain structurally identical so more locales can be
added without changing components. Light, Dark and Auto use semantic CSS variables;
components must not infer theme from hard-coded background colors. Keyboard focus is
always visible, controls retain text labels, layouts work at 320 px, and nonessential
animation stops when `prefers-reduced-motion` is enabled.

The frontend packages fonts into the Vite build. Production still serves static files
and does not need Node or a third-party font service.
