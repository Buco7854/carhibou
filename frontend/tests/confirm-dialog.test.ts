import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import ConfirmDialog from '../src/components/ConfirmDialog.vue'
import { askConfirm, closeConfirm, confirmRequest } from '../src/confirm'

function open() {
  return mount(ConfirmDialog, { global: { plugins: [i18n], stubs: { Teleport: true } } })
}

describe('the one confirmation dialog', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    closeConfirm()
  })

  it('names the subject and states what is lost', async () => {
    const page = open()
    const asked = askConfirm({
      title: 'Delete vehicle', question: 'Delete Éclair?',
      detail: 'Its telemetry goes with it.', confirmLabel: 'Delete vehicle',
    })
    await flushPromises()
    expect(page.get('[role="dialog"]').attributes('aria-label')).toBe('Delete vehicle')
    expect(page.get('.confirm-question').text()).toBe('Delete Éclair?')
    expect(page.text()).toContain('Its telemetry goes with it.')
    expect(page.get('.button.danger').text()).toBe('Delete vehicle')

    await page.get('.button.ghost').trigger('click')
    // Cancelling answers the caller rather than leaving it waiting forever.
    expect(await asked).toBe(false)
  })

  it('runs the action itself, so every caller shows the same progress', async () => {
    const page = open()
    let released: (() => void) | undefined
    const running = new Promise<void>((resolve) => { released = resolve })
    const action = vi.fn(() => running)
    const asked = askConfirm({ title: 'T', question: 'Q', confirmLabel: 'Go', busyLabel: 'Going…', action })
    await flushPromises()
    void page.get('.button.danger').trigger('click')
    await flushPromises()
    expect(action).toHaveBeenCalledTimes(1)
    expect(page.get('.button.danger').text()).toBe('Going…')
    expect(page.get('.button.ghost').attributes('disabled')).toBeDefined()

    released!()
    await flushPromises()
    expect(await asked).toBe(true)
    expect(confirmRequest.value).toBeNull()
  })

  it('holds the dialog open and says why when the action fails', async () => {
    const page = open()
    const asked = askConfirm({
      title: 'T', question: 'Q', confirmLabel: 'Go',
      action: () => Promise.reject(new Error('the server refused')),
    })
    await flushPromises()
    await page.get('.button.danger').trigger('click')
    await flushPromises()
    // A failure that closed the dialog would look like it had worked.
    expect(page.get('[role="alert"]').text()).toBe('the server refused')
    expect(confirmRequest.value).not.toBeNull()
    await page.get('.button.ghost').trigger('click')
    expect(await asked).toBe(false)
  })

  it('offers a second, destructive choice that is never the default', async () => {
    const page = open()
    const chosen: boolean[] = []
    const asked = askConfirm({
      title: 'Remove agent', question: 'Remove Pi?', confirmLabel: 'Remove agent',
      option: { label: 'Also delete everything it recorded', detail: 'This cannot be undone.' },
      action: async (purge) => { chosen.push(purge) },
    })
    await flushPromises()
    const toggle = page.get('.confirm-option input')
    expect((toggle.element as HTMLInputElement).checked).toBe(false)
    await toggle.setValue(true)
    await page.get('.button.danger').trigger('click')
    await flushPromises()
    expect(await asked).toBe(true)
    expect(chosen).toEqual([true])
  })

  it('answers an unfinished question when a second one replaces it', async () => {
    open()
    const first = askConfirm({ title: 'A', question: 'A?', confirmLabel: 'A' })
    askConfirm({ title: 'B', question: 'B?', confirmLabel: 'B' })
    // Otherwise the first caller waits on a promise nothing will ever settle.
    expect(await first).toBe(false)
    expect(confirmRequest.value?.title).toBe('B')
  })
})
