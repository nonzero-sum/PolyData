export function useApiBaseUrl() {
    const config = useRuntimeConfig()
    const nuxtUrl = String(config.public.backendUrl || 'http://127.0.0.1:8000').replace(/\/$/, '')
    return `${nuxtUrl}/api`
}