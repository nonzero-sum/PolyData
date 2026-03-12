const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {}
const backendUrl = env.BACKEND_URL || 'http://127.0.0.1:8000'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  runtimeConfig: {
    backendUrl,
    public: {
      backendUrl,
      nuxtUrl: env.NUXT_URL || 'http://127.0.0.1:3000',
    },
  },
})
