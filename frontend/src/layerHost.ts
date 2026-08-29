/**
 * The one node every floating layer mounts into.
 *
 * Menus, pickers and help bubbles have to escape the panels and table wrappers
 * that clip their overflow, so they teleport out. Two things make this a
 * deliberate node rather than the body itself:
 *
 * - It must not be a container Vue renders. Teleporting into the main element
 *   put foreign children inside a tree Vue owns, and the next route change
 *   diffed them away along with the page it was replacing.
 * - Content parked directly on the body belongs to no landmark, which a screen
 *   reader cannot place and an audit reports. The host is its own landmark, so
 *   whatever it holds is inside one.
 */
let host: HTMLElement | undefined

export function layerHost(): HTMLElement {
  if (!host || !host.isConnected) {
    host = document.createElement('div')
    host.className = 'app-layers'
    host.setAttribute('role', 'region')
    document.body.append(host)
  }
  return host
}

/**
 * A region is only a landmark once it has a name, and the name has to follow the
 * chosen language. The shell owns it because the shell is where the language is.
 */
export function nameLayerHost(label: string): void {
  layerHost().setAttribute('aria-label', label)
}
