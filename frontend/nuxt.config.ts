// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: false },
  ssr: false, // SPA mode for interactive financial dashboards and charts
  modules: [
    '@nuxtjs/tailwindcss'
  ],
  css: [
    '~/assets/css/main.css'
  ],
  app: {
    head: {
      title: 'Кассовый Радар — Банк «Центр-инвест»',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Система предиктивного мониторинга кассовых разрывов с поддержкой ML, Monte Carlo и AI-ассистента GigaChat' }
      ],
      link: [
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap' }
      ]
    }
  },
  nitro: {
    routeRules: {
      '/api/**': {
        proxy: 'http://127.0.0.1:8000/api/**'
      }
    }
  }
})
