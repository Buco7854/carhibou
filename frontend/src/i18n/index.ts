import { createI18n } from 'vue-i18n'
import en from './locales/en'
import fr from './locales/fr'

export const supportedLocales = ['en', 'fr'] as const
export type SupportedLocale = (typeof supportedLocales)[number]

export function detectBrowserLocale(languages: readonly string[] = navigator.languages): SupportedLocale {
  for (const language of languages) {
    const base = language.trim().toLowerCase().split(/[-_]/)[0]
    if (base === 'en' || base === 'fr') return base
  }
  return 'en'
}

function initialLocale(): SupportedLocale {
  const stored = localStorage.getItem('carhibou.locale')
  if (stored === 'en' || stored === 'fr') return stored
  const languages = navigator.languages?.length ? navigator.languages : [navigator.language]
  return detectBrowserLocale(languages)
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
  localStorage.setItem('carhibou.locale', locale)
  document.documentElement.lang = locale
}

document.documentElement.lang = i18n.global.locale.value

export default i18n
