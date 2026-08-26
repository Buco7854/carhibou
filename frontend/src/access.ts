import { computed } from 'vue'
import { auth } from './api/auth'
import type { Vehicle } from './api/types'

/**
 * The server is the enforcement point; these helpers only decide which controls
 * exist. A gate hides its control entirely — a locked door is not drawn.
 * Every view reads its gates from here so a permission is spelled once.
 */
export const isAdmin = computed(() => Boolean(auth.user?.permissions['system.admin']))

/** Profile creation is its own permission, but an administrator never needs it granted. */
export const canCreateProfiles = computed(
  () => Boolean(auth.user?.permissions['profiles.create']) || isAdmin.value,
)

/** The caller's per-vehicle level is computed server-side; an admin arrives as "operate". */
export function canOperate(vehicle: Vehicle | null | undefined): boolean {
  return vehicle?.access === 'operate'
}

export function operableVehicles(vehicles: Vehicle[]): Vehicle[] {
  return vehicles.filter((vehicle) => canOperate(vehicle))
}
