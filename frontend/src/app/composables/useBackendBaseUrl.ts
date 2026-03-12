export function useApiBaseUrl() {
    const config = useRuntimeConfig()
    const nuxtUrl = String(config.public.nuxtUrl || 'http://127.0.0.1:3000').replace(/\/$/, '')

    return `${nuxtUrl}/api`
}