import { createApp } from 'vue'
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-sans/latin-700.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import App from './App.vue'
import i18n from './i18n'
import router from './router'
import { initializeTheme } from './theme'
import './style.css'
import 'gridstack/dist/gridstack.min.css'

initializeTheme()
createApp(App).use(i18n).use(router).mount('#app')
