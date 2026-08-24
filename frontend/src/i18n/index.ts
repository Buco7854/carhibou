import { createI18n } from 'vue-i18n'
import en from './locales/en'
import fr from './locales/fr'

export const supportedLocales = ['en', 'fr'] as const
export type SupportedLocale = (typeof supportedLocales)[number]

function initialLocale(): SupportedLocale {
  const stored = localStorage.getItem('vehinode.locale')
  if (stored === 'en' || stored === 'fr') return stored
  return navigator.language.toLowerCase().startsWith('fr') ? 'fr' : 'en'
}

const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: 'en',
  messages: { en, fr },
  datetimeFormats: {
    en: { short: { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric' } },
    fr: { short: { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric' } },
  },
})

export function persistLocale(locale: SupportedLocale): void {
  localStorage.setItem('vehinode.locale', locale)
  document.documentElement.lang = locale
}

document.documentElement.lang = i18n.global.locale.value

export default i18n
