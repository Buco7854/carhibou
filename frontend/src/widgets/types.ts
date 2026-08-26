import type { Component } from 'vue'
import type { DashboardWidget, Vehicle } from '../api/types'

export interface WidgetSize { w:number; h:number }
export interface DashboardWidgetDefinition {
  type: string
  titleKey: string
  component: Component
  defaultSize: WidgetSize
  needsMetric: boolean
  needsMetrics?: boolean
  configSchema: { fields: string[] }
  /**
   * True when the widget has nothing to show for this vehicle.
   *
   * Only widgets that can answer this from current state define it; widgets that
   * must fetch history first cannot be hidden before they load, so they do not
   * offer the option.
   */
  isEmpty?: (widget: DashboardWidget, vehicle: Vehicle | null | undefined) => boolean
}

export interface WidgetProps { widget:DashboardWidget }
