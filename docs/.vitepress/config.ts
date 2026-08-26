import { defineConfig } from 'vitepress'

export default defineConfig({
  base: process.env.DOCS_BASE ?? '/',
  title: 'VehiNode',
  description: 'Vehicle telemetry, visualization and programmability',
  cleanUrls: true,
  themeConfig: {
    nav: [
      { text: 'Install', link: '/getting-started/installation' },
      { text: 'Use VehiNode', link: '/user-guide/vehicles' },
      { text: 'Vehicle agent', link: '/agent/installation' },
      { text: 'Operate', link: '/operations/deployment' },
      { text: 'Recipes', link: '/recipes/gate-on-arrival' },
    ],
    sidebar: [
      {
        text: 'Start here',
        items: [
          { text: 'Install VehiNode', link: '/getting-started/installation' },
          { text: 'Docker Compose', link: '/getting-started/docker' },
        ],
      },
      {
        text: 'Use VehiNode',
        items: [
          { text: 'Access', link: '/user-guide/access' },
          { text: 'Vehicles', link: '/user-guide/vehicles' },
          { text: 'Agents', link: '/user-guide/devices' },
          { text: 'Dashboards', link: '/user-guide/dashboards' },
          { text: 'History', link: '/user-guide/history' },
          { text: 'Hooks', link: '/user-guide/hooks' },
          { text: 'Secrets', link: '/user-guide/secrets' },
        ],
      },
      {
        text: 'Vehicle agent',
        collapsed: true,
        items: [
          { text: 'Install the agent', link: '/agent/installation' },
          { text: 'Configuration', link: '/agent/configuration' },
          { text: 'Diagnostics', link: '/agent/diagnostics' },
          { text: 'OBDLink SX', link: '/agent/obdlink' },
          { text: 'CAN recording', link: '/agent/can' },
          { text: 'Citroën C-Zero', link: '/agent/c-zero' },
          { text: 'Hardware validation', link: '/agent/hardware-validation' },
        ],
      },
      {
        text: 'Operate',
        items: [
          { text: 'Production checklist', link: '/operations/deployment' },
          { text: 'Backups', link: '/operations/backups' },
          { text: 'Restore', link: '/operations/restore' },
          { text: 'Upgrades', link: '/operations/upgrades' },
          { text: 'Troubleshooting', link: '/operations/troubleshooting' },
        ],
      },
      {
        text: 'Hook recipes',
        items: [
          { text: 'Gate on arrival', link: '/recipes/gate-on-arrival' },
          { text: 'Forward to Traccar', link: '/recipes/traccar' },
          { text: 'Low SOC', link: '/recipes/low-soc' },
          { text: 'Charging finished', link: '/recipes/charging-complete' },
        ],
      },
    ],
    outline: { level: [2, 3], label: 'On this page' },
    editLink: {
      pattern: 'https://github.com/Buco7854/vehinode/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },
    socialLinks: [{ icon: 'github', link: 'https://github.com/Buco7854/vehinode' }],
    search: { provider: 'local' },
  },
})
