# Dashboards

VehiNode always provides one premade **Overview** built from normal widgets, answering in
reading order: where the vehicle is, how much energy is left, whether it is charging and
how fast, what it reports right now, how it has moved, and whether the agent is healthy.
Energy, charging and the photo hide themselves on a vehicle that cannot report them, so
the same preset suits an EV, a fuel vehicle and a car whose agent only sees standard
OBD-II. Existing accounts that predate the preset receive it without losing their other
dashboards. Create additional dashboards for another vehicle or purpose and choose which
one opens by default.

The selected dashboard is the page itself. Tabs sit above the content and a single actions
menu contains **Edit dashboard** and **New dashboard**. Editing enables dragging, resizing
and a compact toolbar on that same canvas. Saving simply removes the editing controls;
there is no separate dashboard-editor destination. Each Overview section is an ordinary
saved widget, so removing or repositioning one in edit mode changes the normal dashboard
page after saving.

Add a widget, select a vehicle and canonical metric, then drag or resize it on a larger
screen. On narrow screens the canvas becomes a single-column stack and moving/resizing
is disabled so widget contents remain readable. Save persists the layout in PostgreSQL.
Available widgets include the vehicle selector, vehicle media, telemetry list, position
map, metric card, energy gauge, status, time series, multi-series comparison, device
health and hook activity. Chart widgets persist their selected one-day, seven-day or
thirty-day range with the layout.

Widgets added with **Selected vehicle** follow the dashboard's selector immediately.
The selector is a fixed-size searchable dropdown, so it does not expand the canvas as the
fleet grows. Widgets pinned to a named vehicle ignore the selector. This allows one
reusable dashboard to switch all of its live cards together while still supporting a
fixed comparison card.

Data widgets use one consistent **No data yet** state until the selected vehicle reports
the required metric, position, history or agent health. Empty maps and charts are not
mounted, and telemetry lists omit unavailable readings instead of filling the card with
dashes.

Widgets that can answer from current state also offer **Hide this widget when the vehicle
reports no data for it**, off by default. A hidden widget leaves no gap: the remaining
widgets close up for that vehicle only, and the saved layout is untouched. Editing always
shows every widget, including hidden ones, so they stay reachable.

The registry maps widget type to component, default size and configuration fields, so
new types remain localized. Dashboards use canonical names such as `battery.soc`, never
CAN identifiers. Suggested metrics come directly from the selected vehicle's reported
keys. The energy gauge shows `battery.soc` when available, otherwise `fuel.level`, without
classifying the vehicle. The charging widget prefers an explicit `charging.active` from a
profile and otherwise derives the state from `battery.power`, which VehiNode treats as
positive while the pack delivers energy and negative while it absorbs it. An explicitly configured metric card or chart always keeps the
metric you selected.

The SPA supports English and French through locale catalogs designed for more languages.
The browser language is used initially; an explicit choice is then saved. Light, Dark
and Auto themes are saved per browser; Auto follows operating-system changes.

## Choosing what a card shows

A card is given patterns rather than a fixed list. A pattern is either an exact
canonical name, `battery.soc`, or a prefix, `tyre.*`. Exact is predictable and is
what a card about one reading wants. A prefix keeps a card correct as a vehicle
gains signals: a card asking for `tyre.*` shows a fourth wheel without being
edited. Both can be mixed, and the order they are written is the order they appear.

How many a card can take is decided by how it draws, not by preference. A gauge is
a proportion of one thing and a reading is one number, so neither has an
arrangement for a second and both take one metric. A table and a chart are lists by
nature and take as many as they are given. A single-value card whose patterns match
several keeps the first the patterns named, so the choice stays yours.
