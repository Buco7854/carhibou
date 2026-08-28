import BatteryGaugeWidget from './BatteryGaugeWidget.vue'
import ChargingWidget from './ChargingWidget.vue'
import ActivityFeedWidget from './ActivityFeedWidget.vue'
import AgentHealthWidget from './AgentHealthWidget.vue'
import HookActivityWidget from './HookActivityWidget.vue'
import MetricCardWidget from './MetricCardWidget.vue'
import MultiSeriesWidget from './MultiSeriesWidget.vue'
import PeriodStatsWidget from './PeriodStatsWidget.vue'
import OnlineStatusWidget from './OnlineStatusWidget.vue'
import PositionMapWidget from './PositionMapWidget.vue'
import RouteMapWidget from './RouteMapWidget.vue'
import SegmentStatsWidget from './SegmentStatsWidget.vue'
import TimeSeriesWidget from './TimeSeriesWidget.vue'
import TelemetryListWidget from './TelemetryListWidget.vue'
import VehicleMediaWidget from './VehicleMediaWidget.vue'
import VehicleSelectorWidget from './VehicleSelectorWidget.vue'
import XyChartWidget from './XyChartWidget.vue'
import type { DashboardWidgetDefinition } from './types'
import type { DashboardWidget, Vehicle } from '../api/types'
import { SPEED_KEY, chargingState, energySummary, metricReading, secondaryReadings } from '../vehicleDisplay'

const reports = (vehicle: Vehicle | null | undefined, key: string): boolean =>
  metricReading(vehicle, key).value !== null

/**
 * Whether a segment-derived card can be hidden.
 *
 * Drives and charges come from an endpoint isEmpty cannot await, so the only
 * signal available at layout time is whether the vehicle has ever reported at
 * all. A vehicle with state but no drives yet keeps its card and says so; only
 * one that has never reported is hidden.
 */
const neverReported = (vehicle: Vehicle | null | undefined): boolean => !vehicle?.state

/*
 * Two types carry no isEmpty, so the editor offers them no hiding toggle.
 * `vehicle-selector` is the control the rest of the board follows: hiding it
 * would strand every other card. `hook-activity` is not vehicle-scoped at all,
 * and isEmpty is only handed a vehicle, so it has nothing to answer from.
 */
const definitions: DashboardWidgetDefinition[] = [
  { type:'vehicle-selector', titleKey:'dashboards.vehicleSelector', component:VehicleSelectorWidget, defaultSize:{w:12,h:1}, general:true, needsMetric:false, configSchema:{fields:['title']} },
  { type:'vehicle-media', titleKey:'dashboards.vehicleMedia', component:VehicleMediaWidget, defaultSize:{w:4,h:2}, general:false, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => !vehicle?.photo_url },
  { type:'telemetry-list', titleKey:'dashboards.telemetryList', component:TelemetryListWidget, defaultSize:{w:4,h:3}, general:true, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => secondaryReadings(vehicle).length === 0 && !reports(vehicle, 'vehicle.speed') },
  { type:'metric-card', titleKey:'dashboards.metricCard', component:MetricCardWidget, defaultSize:{w:3,h:2}, general:false, needsMetric:true, configSchema:{fields:['vehicle_id','metric','title','unit']}, isEmpty:(widget, vehicle) => !reports(vehicle, widget.metric ?? '') },
  { type:'battery-gauge', titleKey:'dashboards.batteryGauge', component:BatteryGaugeWidget, defaultSize:{w:4,h:2}, general:false, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => energySummary(vehicle).value === null },
  { type:'charging', titleKey:'dashboards.charging', component:ChargingWidget, defaultSize:{w:4,h:2}, general:false, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => chargingState(vehicle).active === null },
  { type:'position-map', titleKey:'dashboards.positionMap', component:PositionMapWidget, defaultSize:{w:6,h:4}, general:true, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']}, isEmpty:(_widget, vehicle) => !vehicle?.state?.position },
  { type:'time-series', titleKey:'dashboards.timeSeries', component:TimeSeriesWidget, defaultSize:{w:6,h:3}, general:false, needsMetric:true, configSchema:{fields:['vehicle_id','metric','title','unit','time_range_days']}, isEmpty:(widget, vehicle) => !reports(vehicle, widget.metric ?? '') },
  { type:'multi-series', titleKey:'dashboards.multiSeries', component:MultiSeriesWidget, defaultSize:{w:6,h:3}, general:false, needsMetric:false, needsMetrics:true, configSchema:{fields:['vehicle_id','metrics','title','time_range_days']}, isEmpty:(widget, vehicle) => (widget.metrics ?? []).every((key) => !reports(vehicle, key)) },
  { type:'online-status', titleKey:'dashboards.onlineStatus', component:OnlineStatusWidget, defaultSize:{w:3,h:2}, general:true, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => !vehicle?.state },
  { type:'agent-health', titleKey:'dashboards.agentHealth', component:AgentHealthWidget, defaultSize:{w:3,h:4}, general:true, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => Object.keys(vehicle?.state?.agent ?? {}).length === 0 },
  { type:'route-map', titleKey:'dashboards.routeMap', component:RouteMapWidget, defaultSize:{w:8,h:6}, general:true, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']}, isEmpty:(_widget, vehicle) => !vehicle?.state },
  { type:'activity-feed', titleKey:'dashboards.activityFeed', component:ActivityFeedWidget, defaultSize:{w:4,h:5}, general:true, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']}, isEmpty:(_widget, vehicle) => neverReported(vehicle) },
  { type:'segment-stats', titleKey:'dashboards.segmentStats', component:SegmentStatsWidget, defaultSize:{w:4,h:3}, general:true, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']}, isEmpty:(_widget, vehicle) => neverReported(vehicle) },
  { type:'xy-chart', titleKey:'dashboards.xyChart', component:XyChartWidget, defaultSize:{w:6,h:3}, general:false, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days','x_metric','y_metric']}, isEmpty:(widget, vehicle) => !reports(vehicle, widget.x_metric ?? '') && !reports(vehicle, widget.y_metric ?? '') },
  { type:'period-stats', titleKey:'dashboards.periodStats', component:PeriodStatsWidget, defaultSize:{w:6,h:3}, general:true, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']}, isEmpty:(_widget, vehicle) => neverReported(vehicle) },
  { type:'hook-activity', titleKey:'dashboards.hookActivity', component:HookActivityWidget, defaultSize:{w:4,h:3}, general:true, needsMetric:false, configSchema:{fields:['title']} },
]

export const widgetRegistry: Record<string, DashboardWidgetDefinition> =
  Object.fromEntries(definitions.map((item) => [item.type, item]))

/**
 * Types that were once first class, and the configuration that stands in for
 * them now. This is data migration for saved layouts, not a feature: nothing
 * offers these to the reader, and a card restored through one titles itself
 * from its axes like any other shape.
 */
const LEGACY_TYPES: Record<string, Partial<DashboardWidget> & { type: string }> = {
  'charge-curve': { type: 'xy-chart', x_metric: 'battery.soc', y_metric: 'charging.power' },
}

/** Whether a widget type adapts to any vehicle. */
export function isGeneralChoice(type: string): boolean {
  return widgetRegistry[type]?.general ?? false
}

/**
 * Metric keys every vehicle can answer, whatever its agent can see.
 *
 * Speed is the only one: a CAN or OBD-II agent reports it, and a GNSS-only agent
 * still derives it from the fix, so `speedReading` and `historyValue` resolve it
 * across both sources. A card bound to one of these is asking for standard data
 * and belongs on any dashboard, its empty state reading as ordinary no-data.
 */
export const STANDARD_METRICS: ReadonlySet<string> = new Set([SPEED_KEY])

/**
 * Whether a configured widget depends on data a vehicle may never produce.
 *
 * This is about the instance, not the type. `metric-card` is a data-bound type,
 * because choosing it means choosing a metric, yet an instance bound to speed
 * asks only for standard data and shows unconditionally. An instance bound to
 * battery state does not. A type with no metric field at all (energy, charging,
 * the photo) is bound by its own nature and always counts as specific.
 */
export function needsSpecificData(widget: DashboardWidget): boolean {
  const definition = widgetRegistry[widget.type]
  if (!definition || definition.general) return false
  const bound = [widget.metric, widget.x_metric, widget.y_metric, ...(widget.metrics ?? [])].filter(Boolean)
  return bound.length === 0 || !bound.every((key) => STANDARD_METRICS.has(key!))
}

export function normalizeWidget(widget: DashboardWidget): DashboardWidget {
  const replacement = LEGACY_TYPES[widget.type]
  if (!replacement || widgetRegistry[widget.type]) return widget
  return { ...replacement, ...widget, type: replacement.type }
}
