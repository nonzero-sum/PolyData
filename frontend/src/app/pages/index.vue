<template>
    <main class="hero">
        <div class="hero-card">
            <p class="eyebrow">Open Data Catalog</p>
            <h1>All your data, in the same place.</h1>
            <p class="subtitle">
                A minimal UI to browse public datasets, inspect organizations, and jump into the API without extra
                navigation.
            </p>

            <form class="search-form" @submit.prevent="performSearch">
                <input v-model="searchTerm" type="search" class="search-input" placeholder="Search datasets by title"
                    aria-label="Search datasets" />
                <button class="search-button" type="submit">Search</button>
            </form>

            <div class="meta" aria-label="Catalog summary">
                <NuxtLink class="pill" to="/datasets/">{{ datasetCount }} datasets</NuxtLink>
                <NuxtLink class="pill" to="/resources/">{{ resourceCount }} resources</NuxtLink>
                <NuxtLink class="pill" to="/organizations/">{{ organizationCount }} organizations</NuxtLink>
            </div>
        </div>
    </main>
</template>

<script setup>
import { ref } from 'vue'

const searchTerm = ref('')
const datasetCount = ref(0)
const resourceCount = ref(0)
const organizationCount = ref(0)
const router = useRouter()
const apiBaseUrl = useApiBaseUrl()

function normalizeCount(payload) {
    if (typeof payload?.count === 'number') return payload.count
    if (Array.isArray(payload)) return payload.length
    return 0
}

async function fetchCounts() {
    const [datasetsResponse, resourcesResponse, organizationsResponse] = await Promise.allSettled([
        fetch(`${apiBaseUrl}/datasets/`),
        fetch(`${apiBaseUrl}/resources/`),
        fetch(`${apiBaseUrl}/organizations/`),
    ])

    const datasetsPayload =
        datasetsResponse.status === 'fulfilled' && datasetsResponse.value.ok
            ? await datasetsResponse.value.json()
            : null
    const resourcesPayload =
        resourcesResponse.status === 'fulfilled' && resourcesResponse.value.ok
            ? await resourcesResponse.value.json()
            : null
    const organizationsPayload =
        organizationsResponse.status === 'fulfilled' && organizationsResponse.value.ok
            ? await organizationsResponse.value.json()
            : null

    datasetCount.value = normalizeCount(datasetsPayload)
    resourceCount.value = normalizeCount(resourcesPayload)
    organizationCount.value = normalizeCount(organizationsPayload)
}

async function performSearch() {
    if (!searchTerm.value.trim()) return
    await router.push({ path: '/datasets/', query: { search: searchTerm.value } })
}

await fetchCounts()
</script>

<style scoped>
.hero {
    padding: 56px 0 88px;
}

.hero-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 28px;
    padding: clamp(28px, 5vw, 56px);
    box-shadow: 0 24px 80px rgba(31, 42, 42, 0.08);
    backdrop-filter: blur(8px);
}

.eyebrow {
    margin: 0 0 14px;
    color: var(--accent-dark);
    font-size: 0.82rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
}

h1 {
    margin: 0;
    max-width: 12ch;
    font-size: clamp(3rem, 9vw, 6.2rem);
    line-height: 0.94;
    font-weight: 600;
}

.subtitle {
    margin: 18px 0 0;
    max-width: 56ch;
    color: var(--muted);
    font-size: 1.05rem;
    line-height: 1.7;
}

.search-form {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 12px;
    margin-top: 30px;
}

.search-input {
    width: 100%;
    border: 1px solid rgba(15, 118, 110, 0.22);
    border-radius: 18px;
    padding: 18px 20px;
    font: inherit;
    font-size: 1rem;
    color: var(--ink);
    background: rgba(255, 255, 255, 0.86);
}

.search-button {
    border: 0;
    border-radius: 18px;
    padding: 0 22px;
    min-height: 58px;
    font: inherit;
    font-weight: 700;
    color: white;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%);
    cursor: pointer;
}

.meta {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 22px;
}

.pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 14px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.56);
    color: var(--muted);
    font-size: 0.95rem;
}

.pill:hover {
    color: var(--ink);
    background: rgba(255, 255, 255, 0.82);
}
</style>