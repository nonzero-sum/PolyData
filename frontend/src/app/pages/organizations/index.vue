<template>
    <section class="intro">
        <h1>Organizations</h1>
        <p class="subtitle">A simple directory of the organizations behind the public catalog.</p>

        <form class="search-form" @submit.prevent="performSearch">
            <input v-model="searchTerm" class="search-input search-field" type="search"
                placeholder="Search organizations by title" aria-label="Search organizations" />
            <select v-model="selectedOrdering" class="filter-select" aria-label="Sort organizations">
                <option v-for="option in orderingOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                </option>
            </select>
            <button class="search-button" type="submit">Apply</button>
        </form>
    </section>

    <section v-if="organizationItems.length" class="grid">
        <NuxtLink v-for="organization in organizationItems" :key="organization.id" class="card"
            :to="`/organizations/${organization.id}`">
            <h2>{{ organization.title }}</h2>
            <p>{{ organization.description || 'No description yet.' }}</p>
            <div class="meta">
                <div v-if="organization.url">{{ organization.url }}</div>
                <div v-if="organization.email">{{ organization.email }}</div>
            </div>
        </NuxtLink>
    </section>

    <div v-else class="empty">No organizations matched this search.</div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const organizations = ref([])
const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const searchTerm = ref(typeof route.query.search === 'string' ? route.query.search : '')
const selectedOrdering = ref(typeof route.query.ordering === 'string' ? route.query.ordering : 'title')
const organizationItems = computed(() => Array.isArray(organizations.value) ? organizations.value : [])

const orderingOptions = [
    { value: 'title', label: 'Title A-Z' },
    { value: '-title', label: 'Title Z-A' },
]

async function fetchOrganizations() {
    const base = config.public.backendUrl || 'http://localhost:8000'
    const url = new URL(`${base}/api/organizations/`)
    const query = typeof route.query.search === 'string' ? route.query.search.trim() : ''
    searchTerm.value = query
    selectedOrdering.value = typeof route.query.ordering === 'string' ? route.query.ordering : 'title'
    if (query) url.searchParams.set('search', query)
    if (selectedOrdering.value) url.searchParams.set('ordering', selectedOrdering.value)
    const res = await fetch(url.toString())
    if (res.ok) {
        const data = await res.json()
        organizations.value = data.results || data
    } else {
        organizations.value = []
    }
}

async function performSearch() {
    const nextQuery = {}
    const query = searchTerm.value.trim()
    if (query) nextQuery.search = query
    if (selectedOrdering.value && selectedOrdering.value !== 'title') nextQuery.ordering = selectedOrdering.value
    await router.push({ path: '/organizations/', query: nextQuery })
}

await fetchOrganizations()
watch(() => route.fullPath, fetchOrganizations)
</script>

<style scoped>
.intro {
    padding: 24px 0 12px;
}

h1 {
    margin: 0;
    font-size: clamp(2.4rem, 6vw, 4.4rem);
}

.subtitle {
    color: var(--muted);
    max-width: 58ch;
    line-height: 1.7;
}

.search-form {
    display: grid;
    grid-template-columns: minmax(240px, 2fr) minmax(0, 1fr) auto;
    gap: 12px;
    margin: 24px 0 30px;
}

.search-input,
.filter-select {
    border: 1px solid rgba(15, 118, 110, 0.22);
    border-radius: 18px;
    padding: 16px 18px;
    font: inherit;
    background: rgba(255, 255, 255, 0.86);
}

.search-field {
    width: 100%;
}

.search-button {
    border: 0;
    border-radius: 18px;
    padding: 0 22px;
    min-height: 54px;
    font: inherit;
    font-weight: 700;
    color: white;
    background: var(--accent);
    cursor: pointer;
}

.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
    padding-bottom: 56px;
}

.card {
    display: block;
    border: 1px solid var(--line);
    border-radius: 24px;
    padding: 22px;
    background: var(--card);
}

.card h2 {
    margin: 0 0 12px;
    font-size: 1.35rem;
}

.card p {
    margin: 0 0 14px;
    color: var(--muted);
    line-height: 1.6;
}

.meta {
    color: var(--muted);
    font-size: 0.95rem;
}

.empty {
    padding: 28px;
    border: 1px dashed var(--line);
    border-radius: 24px;
    color: var(--muted);
    background: rgba(255, 255, 255, 0.42);
}

@media (max-width: 960px) {
    .search-form {
        grid-template-columns: 1fr 1fr;
    }
}

@media (max-width: 640px) {
    .search-form {
        grid-template-columns: 1fr;
    }
}
</style>