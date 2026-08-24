import { defineConfig } from 'vitepress'

export default defineConfig({
  base: process.env.DOCS_BASE ?? '/',
  title: 'VehiNode',
  description: 'Vehicle telemetry, visualization and programmability',
  cleanUrls: true,
  themeConfig: {
    nav: [
      { text: 'Get started', link: '/getting-started/installation' },
      { text: 'User guide', link: '/user-guide/vehicles' },
      { text: 'Agent', link: '/agent/installation' },
      { text: 'Developers', link: '/developers/architecture' },
      { text: 'Operations', link: '/operations/deployment' },
    ],
    sidebar: [
      { text:'Getting started',items:[{text:'Installation',link:'/getting-started/installation'},{text:'Docker',link:'/getting-started/docker'},{text:'Development',link:'/getting-started/development'}]},
      { text:'User guide',items:[{text:'Vehicles',link:'/user-guide/vehicles'},{text:'Dashboards',link:'/user-guide/dashboards'},{text:'History',link:'/user-guide/history'},{text:'Hooks',link:'/user-guide/hooks'},{text:'Secrets',link:'/user-guide/secrets'},{text:'Devices',link:'/user-guide/devices'}]},
      { text:'Vehicle agent',items:[{text:'Installation',link:'/agent/installation'},{text:'Configuration',link:'/agent/configuration'},{text:'Diagnostics',link:'/agent/diagnostics'},{text:'OBDLink SX',link:'/agent/obdlink'},{text:'CAN',link:'/agent/can'},{text:'C-Zero',link:'/agent/c-zero'},{text:'Hardware validation',link:'/agent/hardware-validation'}]},
      { text:'Developers',items:[{text:'Architecture',link:'/developers/architecture'},{text:'API',link:'/developers/api'},{text:'Authentication',link:'/developers/auth'},{text:'Telemetry',link:'/developers/telemetry'},{text:'Vehicle profiles',link:'/developers/vehicle-profiles'},{text:'Hook runtime',link:'/developers/hook-runtime'},{text:'Future events',link:'/developers/future-events'},{text:'Definition of Done',link:'/developers/definition-of-done'}]},
      { text:'Operations',items:[{text:'Deployment',link:'/operations/deployment'},{text:'Backups',link:'/operations/backups'},{text:'Restore',link:'/operations/restore'},{text:'Upgrades',link:'/operations/upgrades'},{text:'Troubleshooting',link:'/operations/troubleshooting'}]},
      { text:'Recipes',items:[{text:'Gate on arrival',link:'/recipes/gate-on-arrival'},{text:'Traccar',link:'/recipes/traccar'},{text:'Low SOC',link:'/recipes/low-soc'}]},
    ],
    socialLinks: [{ icon:'github',link:'https://github.com/vehinode/vehinode' }],
    search: { provider:'local' },
  },
})
