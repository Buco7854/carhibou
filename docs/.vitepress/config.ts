import { defineConfig } from 'vitepress'

export default defineConfig({
  base: process.env.DOCS_BASE ?? '/',
  head: [
    ['link', { rel: 'icon', href: '/carhibou-mark.svg', type: 'image/svg+xml', media: '(prefers-color-scheme: light)' }],
    ['link', { rel: 'icon', href: '/carhibou-mark-dark.svg', type: 'image/svg+xml', media: '(prefers-color-scheme: dark)' }],
    ['meta', { property: 'og:title', content: 'Carhibou: vehicle telemetry' }],
    ['meta', { property: 'og:description', content: 'Collect GPS, OBD-II and CAN data from your cars, inspect it in the browser, and react with trusted Python hooks.' }],
    ['meta', { property: 'og:image', content: 'https://buco7854.github.io/carhibou/og.png' }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
  ],
  title: 'Carhibou',
  description: 'Vehicle telemetry, visualization and programmability',
  cleanUrls: true,
  themeConfig: {
    logo: { light: '/carhibou-mark.svg', dark: '/carhibou-mark-dark.svg' },
    nav: [
      { text: 'Install', link: '/getting-started/installation' },
      { text: 'Use Carhibou', link: '/user-guide/vehicles' },
      { text: 'Vehicle agent', link: '/agent/agent' },
      { text: 'Develop', link: '/developers/architecture' },
    ],
    sidebar: [
      {
        text: 'Start here',
        items: [{ text: 'Install Carhibou', link: '/getting-started/installation' }],
      },
      {
        text: 'Use Carhibou',
        items: [
          { text: 'Access', link: '/user-guide/access' },
          { text: 'Vehicles and history', link: '/user-guide/vehicles' },
          { text: 'Dashboards', link: '/user-guide/dashboards' },
          { text: 'Agents', link: '/user-guide/devices' },
          { text: 'Hooks and secrets', link: '/user-guide/hooks' },
        ],
      },
      {
        text: 'Vehicle agent',
        items: [
          { text: 'Install and configure', link: '/agent/agent' },
          { text: 'Diagnostics and validation', link: '/agent/diagnostics' },
        ],
      },
      {
        text: 'Develop',
        items: [
          { text: 'Architecture', link: '/developers/architecture' },
          { text: 'Vehicle profiles', link: '/developers/vehicle-profiles' },
        ],
      },
    ],
    outline: { level: [2, 3], label: 'On this page' },
    editLink: {
      pattern: 'https://github.com/Buco7854/carhibou/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },
    socialLinks: [{ icon: 'github', link: 'https://github.com/Buco7854/carhibou' }],
    search: { provider: 'local' },
  },
})
