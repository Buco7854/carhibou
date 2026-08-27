export interface LatLng { lat: number; lng: number }

const EARTH_RADIUS_KM = 6371

export function haversineKm(from: LatLng, to: LatLng): number {
  const toRad = (degrees: number) => (degrees * Math.PI) / 180
  const deltaLat = toRad(to.lat - from.lat)
  const deltaLng = toRad(to.lng - from.lng)
  const a = Math.sin(deltaLat / 2) ** 2
    + Math.cos(toRad(from.lat)) * Math.cos(toRad(to.lat)) * Math.sin(deltaLng / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)))
}

/** Summed leg distance along an ordered path. */
export function pathLengthKm(points: LatLng[]): number {
  let total = 0
  for (let index = 0; index < points.length - 1; index += 1) total += haversineKm(points[index]!, points[index + 1]!)
  return total
}
