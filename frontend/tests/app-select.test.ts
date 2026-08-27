import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AppSelect from '../src/components/AppSelect.vue'

describe('AppSelect', () => {
  it('renders an application-owned listbox instead of a native select', async () => {
    const wrapper = mount(AppSelect, {
      props: { modelValue:'one' },
      slots: { default:'<option value="one">First option</option><option value="two">Second option</option>' },
      global: { stubs:{Teleport:true} },
    })

    expect(wrapper.find('select').exists()).toBe(false)
    expect(wrapper.get('[role="combobox"]').text()).toContain('First option')
    await wrapper.get('[role="combobox"]').trigger('click')
    expect(wrapper.findAll('[role="option"]')).toHaveLength(2)
    await wrapper.findAll('[role="option"]')[1]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['two'])
  })

  it('supports keyboard selection', async () => {
    const wrapper = mount(AppSelect, {
      props: { modelValue:1 },
      slots: { default:'<option :value="1">One</option><option :value="2">Two</option>' },
      global: { stubs:{Teleport:true} },
    })
    const trigger = wrapper.get('[role="combobox"]')
    await trigger.trigger('keydown', { key:'ArrowDown' })
    await trigger.trigger('keydown', { key:'ArrowDown' })
    await trigger.trigger('keydown', { key:'Enter' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([2])
  })

  it('filters a large option list when search is enabled', async () => {
    const vehicleOptions = [
      '<option value="vehicle-0">Éclair</option>',
      ...Array.from({ length:100 }, (_, index) => `<option value="vehicle-${index + 1}">Vehicle ${index + 1}</option>`),
    ].join('')
    const wrapper = mount(AppSelect, {
      props: {
        modelValue:'vehicle-0',
        searchable:true,
        searchPlaceholder:'Search vehicles',
        noResultsText:'No vehicles found',
      },
      slots: { default:vehicleOptions },
      global: { stubs:{Teleport:true} },
    })

    await wrapper.get('[role="combobox"]').trigger('click')
    await wrapper.get('input[type="search"]').setValue('ecl')
    expect(wrapper.findAll('[role="option"]')).toHaveLength(1)
    expect(wrapper.get('[role="option"]').text()).toContain('Éclair')
    await wrapper.get('input[type="search"]').setValue('missing')
    expect(wrapper.find('[role="option"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('No vehicles found')
  })
})
