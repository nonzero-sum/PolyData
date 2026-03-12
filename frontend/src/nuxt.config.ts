const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {}

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  runtimeConfig: {
    backendUrl: env.BACKEND_URL || 'http://backend:8000',
    public: {
      nuxtUrl: env.NUXT_URL || 'http://127.0.0.1:3000',
    },
  },
})
