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
  /**
   * True when the widget adapts to whatever the vehicle reports, so it belongs
   * in a dashboard unconditionally and its empty state is itself an answer.
   *
   * False when it is bound to named data a vehicle may never produce. Those are
   * grouped apart in the picker and default to hiding themselves, because a
   * permanently blank card claims the vehicle should have data it cannot send.
   * This is the one place the distinction is declared; the picker, the hide
   * default and the premade layout all read it from here.
   */
  general: boolean
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

