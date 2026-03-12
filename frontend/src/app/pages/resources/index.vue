<template>
    <section class="intro">
        <h1>Resources</h1>
        <p class="subtitle">Browse all public resources and filter them by text, type, tag, or sort order.</p>

        <form class="search-form" @submit.prevent="performSearch">
            <input v-model="searchTerm" class="search-input search-field" type="search"
                placeholder="Search resources by title" aria-label="Search resources" />
            <select v-model="selectedType" class="filter-select" aria-label="Filter by resource type">
                <option value="">All types</option>
                <option v-for="kind in resourceKindOptions" :key="kind.value" :value="kind.value">
                    {{ kind.label }}
                </option>
            </select>
            <select v-model="selectedOrdering" class="filter-select" aria-label="Sort resources">
                <option v-for="option in orderingOptions" :key="option.value" :value="option.value">
                    {{ option.label }}
                </option>
            </select>
            <button class="search-button" type="submit">Apply</button>
        </form>

        <div v-if="tagOptions.length" class="filters" aria-label="Resource tag filters">
            <button class="filter-pill" :class="{ active: !selectedTag }" type="button" @click="selectTag('')">
                All tags
            </button>
            <button v-for="tag in tagOptions" :key="tag.id" class="filter-pill"
                :class="{ active: selectedTag === tag.slug }" type="button" @click="selectTag(tag.slug)">
                {{ tag.name }}
            </button>
        </div>
    </section>

    <section v-if="resourceItems.length" class="grid">
        <NuxtLink v-for="resource in resourceItems" :key="resource.id" class="card" :to="`/resources/${resource.id}`">
            <div class="kind-pill">{{ formatLabel(resource.resource_kind) }}</div>
            <h2>{{ resource.title }}</h2>
            <p>{{ resource.description || 'No description yet.' }}</p>
            <div class="meta">
                <div v-if="resource.media_type">Media type: {{ resource.media_type }}</div>
            </div>
            <div v-if="resource.dataset_tags?.length" class="tag-row">
                <span v-for="tag in resource.dataset_tags" :key="tag" class="tag-pill">{{ tag }}</span>
            </div>
        </NuxtLink>
    </section>

    <div v-else class="empty">No resources matched the current search.</div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const resources = ref([])
const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const searchTerm = ref(typeof route.query.search === 'string' ? route.query.search : '')
const selectedType = ref(typeof route.query.type === 'string' ? route.query.type : '')
const selectedTag = ref(typeof route.query.tag === 'string' ? route.query.tag : '')
const selectedOrdering = ref(typeof route.query.ordering === 'string' ? route.query.ordering : 'title')
const filterOptions = ref({ resourceKinds: [], tags: [] })
const resourceItems = computed(() => Array.isArray(resources.value) ? resources.value : [])
const resourceKindOptions = computed(() => filterOptions.value?.resourceKinds ?? [])
const tagOptions = computed(() => filterOptions.value?.tags ?? [])

const orderingOptions = [
    { value: 'title', label: 'Title A-Z' },
    { value: '-title', label: 'Title Z-A' },
    { value: '-updated_at', label: 'Recently updated' },
]

function formatLabel(value) {
    if (!value) return 'Unknown'
    return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

async function fetchResources() {
    const base = config.public.backendUrl || 'http://localhost:8000'
    const url = new URL(`${base}/api/resources/`)
    const query = typeof route.query.search === 'string' ? route.query.search.trim() : ''
    searchTerm.value = query
    selectedType.value = typeof route.query.type === 'string' ? route.query.type : ''
    selectedTag.value = typeof route.query.tag === 'string' ? route.query.tag : ''
    selectedOrdering.value = typeof route.query.ordering === 'string' ? route.query.ordering : 'title'
    if (query) url.searchParams.set('search', query)
    if (selectedType.value) url.searchParams.set('type', selectedType.value)
    if (selectedTag.value) url.searchParams.set('tag', selectedTag.value)
    if (selectedOrdering.value) url.searchParams.set('ordering', selectedOrdering.value)
    const res = await fetch(url.toString())
    if (res.ok) {
        const data = await res.json()
        resources.value = data.results || data
    } else {
        resources.value = []
    }
}

async function fetchFilterOptions() {
    const base = config.public.backendUrl || 'http://localhost:8000'
    const res = await fetch(`${base}/api/resources/filter-options/`)
    if (!res.ok) return
    const data = await res.json()
    filterOptions.value = {
        resourceKinds: data.resource_kinds || [],
        tags: data.tags || [],
    }
}

async function performSearch() {
    const nextQuery = {}
    const query = searchTerm.value.trim()
    if (query) nextQuery.search = query
    if (selectedType.value) nextQuery.type = selectedType.value
    if (selectedTag.value) nextQuery.tag = selectedTag.value
    if (selectedOrdering.value && selectedOrdering.value !== 'title') nextQuery.ordering = selectedOrdering.value
    await router.push({ path: '/resources/', query: nextQuery })
}

async function selectTag(tagSlug) {
    selectedTag.value = tagSlug
    await performSearch()
}

await Promise.all([fetchResources(), fetchFilterOptions()])
watch(() => route.fullPath, fetchResources)
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
    grid-template-columns: minmax(220px, 2fr) repeat(2, minmax(0, 1fr)) auto;
    gap: 12px;
    margin: 24px 0 24px;
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

.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
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
    display: grid;
    gap: 6px;
}

.kind-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 10px;
    padding: 7px 10px;
    border-radius: 999px;
    background: rgba(15, 118, 110, 0.08);
    color: var(--accent);
    font-size: 0.82rem;
}

.tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 14px;
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

@media (max-width: 1080px) {
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