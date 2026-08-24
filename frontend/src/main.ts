import { createApp } from 'vue'
import App from './App.vue'
import i18n from './i18n'
import router from './router'
import { initializeTheme } from './theme'
import './style.css'
import 'leaflet/dist/leaflet.css'
import 'gridstack/dist/gridstack.min.css'

initializeTheme()
createApp(App).use(i18n).use(router).mount('#app')
