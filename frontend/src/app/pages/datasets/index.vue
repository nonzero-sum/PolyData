<template>
    <section class="intro">
        <h1>Datasets</h1>
        <p class="subtitle">Browse the public catalog and filter datasets by title, organization, tag, and metadata.</p>

        <form class="search-form" @submit.prevent="performSearch">
            <input v-model="searchTerm" class="search-input search-field" type="search" placeholder="Search Datasets"
                aria-label="Search datasets" />
            <select v-model="selectedOrganization" class="filter-select" aria-label="Filter by organization">
                <option value="">All organizations</option>
                <option v-for="organization in organizationOptions" :key="organization.id" :value="organization.slug">
                    {{ organization.title }}
                </option>
            </select>
            <select v-model="selectedFrequency" class="filter-select" aria-label="Filter by update frequency">
                <option value="">Any frequency</option>
                <option v-for="frequency in updateFrequencyOptions" :key="frequency.value" :value="frequency.value">
                    {{ frequency.label }}
                </option>
            </select>
            <select v-model="selectedOrdering" class="filter-select" aria-label="Sort datasets">
                <option v-for="option in orderingOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                </option>
            </select>
            <button class="search-button" type="submit">Apply</button>
        </form>

        <div v-if="tagOptions.length" class="filters" aria-label="Dataset tag filters">
            <button class="filter-pill" :class="{ active: !selectedTag }" type="button" @click="selectTag('')">
                All tags
            </button>
            <button v-for="tag in tagOptions" :key="tag.id" class="filter-pill"
                :class="{ active: selectedTag === tag.slug }" type="button" @click="selectTag(tag.slug)">
                {{ tag.name }}
            </button>
        </div>
    </section>

    <section v-if="datasetItems.length" class="grid">
        <NuxtLink v-for="dataset in datasetItems" :key="dataset.id" class="card" :to="`/datasets/${dataset.id}`">
            <h2>{{ dataset.title }}</h2>
            <p>{{ dataset.description || 'No description yet.' }}</p>
            <div class="meta">
                <div v-if="dataset.organization">Organization: {{ dataset.organization.title }}</div>
                <div v-if="dataset.update_frequency">Frequency: {{ formatFrequency(dataset.update_frequency) }}</div>
            </div>
            <div v-if="dataset.tags?.length" class="tag-row">
                <span v-for="tag in dataset.tags" :key="tag" class="tag-pill">{{ tag }}</span>
            </div>
        </NuxtLink>
    </section>

    <div v-else class="empty">No datasets matched the current search.</div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const datasets = ref([])
const route = useRoute()
const router = useRouter()
const apiBaseUrl = useApiBaseUrl()
const searchTerm = ref(typeof route.query.search === 'string' ? route.query.search : '')
const selectedOrganization = ref(typeof route.query.organization === 'string' ? route.query.organization : '')
const selectedTag = ref(typeof route.query.tag === 'string' ? route.query.tag : '')
const selectedFrequency = ref(typeof route.query.update_frequency === 'string' ? route.query.update_frequency : '')
const selectedOrdering = ref(typeof route.query.ordering === 'string' ? route.query.ordering : 'title')
const filterOptions = ref({ organizations: [], tags: [], updateFrequencies: [] })
const datasetItems = computed(() => Array.isArray(datasets.value) ? datasets.value : [])
const organizationOptions = computed(() => filterOptions.value?.organizations ?? [])
const tagOptions = computed(() => filterOptions.value?.tags ?? [])
const updateFrequencyOptions = computed(() => filterOptions.value?.updateFrequencies ?? [])

const orderingOptions = [
    { value: 'title', label: 'Title A-Z' },
    { value: '-title', label: 'Title Z-A' },
    { value: '-updated_at', label: 'Recently updated' },
    { value: '-created_at', label: 'Newest first' },
]

function formatFrequency(value) {
    return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

async function fetchData() {
    const url = new URL(`${apiBaseUrl}/datasets/`)
    const query = typeof route.query.search === 'string' ? route.query.search.trim() : ''
    searchTerm.value = query
    selectedOrganization.value = typeof route.query.organization === 'string' ? route.query.organization : ''
    selectedTag.value = typeof route.query.tag === 'string' ? route.query.tag : ''
    selectedFrequency.value = typeof route.query.update_frequency === 'string' ? route.query.update_frequency : ''
    selectedOrdering.value = typeof route.query.ordering === 'string' ? route.query.ordering : 'title'
    if (query) url.searchParams.set('search', query)
    if (selectedOrganization.value) url.searchParams.set('organization', selectedOrganization.value)
    if (selectedTag.value) url.searchParams.set('tag', selectedTag.value)
    if (selectedFrequency.value) url.searchParams.set('update_frequency', selectedFrequency.value)
    if (selectedOrdering.value) url.searchParams.set('ordering', selectedOrdering.value)
    const res = await fetch(url.toString())
    if (res.ok) {
        const data = await res.json()
        datasets.value = data.results || data
    } else {
        datasets.value = []
    }
}

async function fetchFilterOptions() {
    const res = await fetch(`${apiBaseUrl}/datasets/filter-options/`)
    if (!res.ok) return
    const data = await res.json()
    filterOptions.value = {
        organizations: data.organizations || [],
        tags: data.tags || [],
        updateFrequencies: data.update_frequencies || [],
    }
}

async function performSearch() {
    const nextQuery = {}
    const query = searchTerm.value.trim()
    if (query) nextQuery.search = query
    if (selectedOrganization.value) nextQuery.organization = selectedOrganization.value
    if (selectedTag.value) nextQuery.tag = selectedTag.value
    if (selectedFrequency.value) nextQuery.update_frequency = selectedFrequency.value
    if (selectedOrdering.value && selectedOrdering.value !== 'title') nextQuery.ordering = selectedOrdering.value
    await router.push({ path: '/datasets/', query: nextQuery })
}

async function selectTag(tagSlug) {
    selectedTag.value = tagSlug
    await performSearch()
}

await Promise.all([fetchData(), fetchFilterOptions()])
watch(() => route.fullPath, fetchData)
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
    grid-template-columns: minmax(240px, 2fr) repeat(3, minmax(0, 1fr)) auto;
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

.tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 14px;
}

.filters {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: -8px 0 24px;
}

.filter-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 14px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.68);
    color: var(--muted);
    font-size: 0.94rem;
    cursor: pointer;
}

.filter-pill.active {
    background: rgba(15, 118, 110, 0.12);
    border-color: rgba(15, 118, 110, 0.24);
    color: var(--accent);
}

.tag-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 7px 10px;
    border-radius: 999px;
    background: rgba(15, 118, 110, 0.08);
    color: var(--accent);
    font-size: 0.82rem;
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