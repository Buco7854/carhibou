# History

History covers one vehicle over a chosen range. Pick the metric and range once: the
chart, the route map and the table all follow that choice.

## Chart and route

The chart endpoint bounds its result and downsamples to the requested maximum, so a month
of raw samples never reaches the browser in one response. The metric list is built from
what the vehicle actually reported, so a profile that decodes vehicle-specific signals
makes them selectable here without any extra configuration.

## Table of entries

**All entries** lists raw rows, newest first. It is paginated rather than downsampled, so
what you see is exactly what was stored.

- **Sort** by clicking any header. Metric columns sort numerically; values that are not
  numbers (booleans, text) sort last rather than failing the query.
- **Filter** on one numeric column with a minimum, a maximum, or both. *Only rows
  reporting it* hides rows where that signal is absent, which is useful for a signal that
  a profile decodes intermittently.
- **Columns** lets you hide columns and reorder them. The choice is remembered per vehicle
  in your browser, and signals that appear later are appended rather than replacing it.

Columns come from the data, not a fixed list: position and device fields plus one column
per metric the vehicle reported in the range. Two vehicles with different profiles
therefore show different columns.
