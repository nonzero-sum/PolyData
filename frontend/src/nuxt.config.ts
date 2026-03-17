const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {}
const backendUrl = env.BACKEND_URL

if (!backendUrl) {
  throw new Error(
    'Missing required environment variable BACKEND_URL. Set BACKEND_URL to the backend API base URL.'
  )
}

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  ssr: false,
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
