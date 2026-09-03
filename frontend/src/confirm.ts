import { ref, shallowRef } from 'vue'

/**
 * One confirmation, asked the same way everywhere.
 *
 * This replaces window.confirm, which could not name a subject in the app's own
 * voice, could not be translated, could not show what a destructive choice
 * costs, and looked like the browser rather than like Carhibou. Because the
 * dialog also runs the action, every caller gets the same busy state and the
 * same error handling instead of the nine different amounts of it they had.
 */
export interface ConfirmOption {
  label: string
  /** What choosing it costs, stated plainly. */
  detail?: string
}

export interface ConfirmRequest {
  title: string
  /** Names the subject: "Delete Éclair?" */
  question: string
  /** What is lost, or kept. */
  detail?: string
  confirmLabel: string
  busyLabel?: string
  /** A second, destructive choice inside the confirmation. Defaults to off. */
  option?: ConfirmOption
  /** Run while the dialog holds, so it can show progress and report failure. */
  action?: (option: boolean) => Promise<void>
}

export const confirmRequest = shallowRef<ConfirmRequest | null>(null)
export const confirmOption = ref(false)
export const confirmBusy = ref(false)
export const confirmError = ref('')

let settle: ((accepted: boolean) => void) | null = null

/** Resolves true once the reader accepted and any action succeeded. */
export function askConfirm(request: ConfirmRequest): Promise<boolean> {
  // A second question while one is open would replace it and strand its caller.
  settle?.(false)
  confirmRequest.value = request
  confirmOption.value = false
  confirmError.value = ''
  confirmBusy.value = false
  return new Promise<boolean>((resolve) => { settle = resolve })
}

export function closeConfirm(): void {
  if (confirmBusy.value) return
  confirmRequest.value = null
  settle?.(false)
  settle = null
}

export async function acceptConfirm(): Promise<void> {
  const request = confirmRequest.value
  if (!request || confirmBusy.value) return
  const chosen = confirmOption.value
  if (request.action) {
    confirmBusy.value = true
    confirmError.value = ''
    try {
      await request.action(chosen)
    } catch (reason) {
      confirmError.value = reason instanceof Error && reason.message ? reason.message : 'error'
      return
    } finally {
      confirmBusy.value = false
    }
  }
  confirmRequest.value = null
  settle?.(true)
  settle = null
}
