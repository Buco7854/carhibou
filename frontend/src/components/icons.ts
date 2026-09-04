import type { Component } from 'vue'
import {
  ArrowLeft, BatteryCharging, BatteryMedium, Camera, Car, Check, ChevronDown, ChevronUp,
  Columns3, Copy, Cpu, Ellipsis, Expand, Fuel, Gauge, History, ImageOff, Info, LayoutGrid, LogOut, MapPin, Minus, Pencil, Plus, Search, Settings, ShieldCheck, Signal,
  SlidersHorizontal, SunMedium, Thermometer, Trash2, TriangleAlert, Webhook, X, Zap,
} from 'lucide-vue-next'

/**
 * The application's icon vocabulary, mapped onto one library.
 *
 * Callers name what a thing *is* rather than which glyph to draw, because half
 * of these names arrive at runtime: a metric definition carries `icon: 'battery'`
 * and a widget's empty state carries `icon: 'location'`. Keeping that indirection
 * means the drawing can change without touching the data that asks for it, and
 * it keeps one place to check that the set stays coherent.
 *
 * Icons are bundled from the dependency and tree-shaken by these named imports;
 * nothing is fetched at runtime, matching how the typography is self-hosted.
 */
export const ICONS: Record<string, Component> = {
  // Navigation and structure.
  grid: LayoutGrid,
  vehicle: Car,
  profile: SlidersHorizontal,
  hooks: Webhook,
  agent: Cpu,
  settings: Settings,
  shield: ShieldCheck,
  history: History,

  // Actions.
  plus: Plus,
  minus: Minus,
  edit: Pencil,
  trash: Trash2,
  copy: Copy,
  expand: Expand,
  search: Search,
  close: X,
  check: Check,
  more: Ellipsis,
  signout: LogOut,
  theme: SunMedium,
  camera: Camera,
  columns: Columns3,
  'arrow-left': ArrowLeft,
  'chevron-down': ChevronDown,
  'chevron-up': ChevronUp,

  // Readings, named for what they measure.
  battery: BatteryMedium,
  charging: BatteryCharging,
  energy: Zap,
  fuel: Fuel,
  speed: Gauge,
  temperature: Thermometer,
  signal: Signal,
  location: MapPin,

  // States.
  alert: TriangleAlert,
  info: Info,
  'image-missing': ImageOff,
}
