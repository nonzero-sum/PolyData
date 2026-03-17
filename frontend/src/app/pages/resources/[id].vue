<template>
    <div v-if="resource">
        <section class="hero">
            <p class="eyebrow">Resource Detail</p>
            <h1>{{ resource.title }}</h1>
            <p class="lead">{{ resource.description || 'No description yet.' }}</p>

            <div class="button-row">
                <NuxtLink class="button-link" :to="`/datasets/${resource.dataset}`">Back to dataset</NuxtLink>
                <a v-if="resource.file_representation?.download_url" class="button-link primary"
                    :href="resource.file_representation.download_url">Download</a>
            </div>

            <div v-if="resource.dataset_tags?.length" class="tag-row">
                <span v-for="tag in resource.dataset_tags" :key="tag" class="tag-pill">{{ tag }}</span>
            </div>
        </section>

        <section class="layout">
            <div class="panel">
                <h2>Preview</h2>

                <div v-if="hasMapPreview" class="preview-grid">
                    <ResourceMapPreview :collectionUrl="mapCollectionUrl" :bounds="mapBounds" />
                </div>

                <div v-if="resource.tables?.length" class="preview-grid">
                    <ResourceTablePreview v-for="table in resource.tables" :key="table.id" :rowsUrl="table.rows_url" />
                </div>

                <div v-if="!hasMapPreview && !resource.tables?.length" class="table-meta">
                    No preview available for this resource.
                </div>
            </div>

            <aside class="panel">
                <h2>Metadata</h2>
                <div class="facts">
                    <div><span class="fact-label">Kind</span>{{ formatLabel(resource.resource_kind) }}</div>
                    <div><span class="fact-label">Slug</span>{{ resource.slug }}</div>
                    <div v-if="resource.media_type"><span class="fact-label">Media Type</span>{{ resource.media_type }}
                    </div>
                    <div><span class="fact-label">Published</span>{{ resource.published ? 'Yes' : 'No' }}</div>
                </div>
            </aside>
        </section>
    </div>

    <p v-else>Loading...</p>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'

const resource = ref(null)
const route = useRoute()
const apiBaseUrl = useApiBaseUrl()

const mapTable = computed(() => {
    // Prefer spatial table with OGC API support.
    const tables = resource.value?.tables || []
    return tables.find((table) => table.ogc_collection_url) ?? tables[0] ?? null
})

const hasMapPreview = computed(() => !!mapTable.value && !!mapTable.value.ogc_collection_url)
const mapCollectionUrl = computed(() => mapTable.value?.ogc_collection_url || '')
const mapBounds = computed(() => mapTable.value?.bbox || null)

function formatLabel(value) {
    if (!value) return 'Unknown'
    return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

async function fetchResource() {
    const res = await fetch(`${apiBaseUrl}/resources/${route.params.id}/`)
    resource.value = res.ok ? await res.json() : null
}

if (process.client) {
    onMounted(fetchResource)
    watch(() => route.params.id, fetchResource)
}
</script>

<style scoped>
.hero {
    padding: 24px 0;
}

.eyebrow {
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.82rem;
    margin: 0 0 10px;
}

h1 {
    margin: 0;
    font-size: clamp(2.6rem, 6vw, 4.6rem);
    line-height: 0.98;
}

.lead {
    color: var(--muted);
    max-width: 62ch;
    line-height: 1.7;
    margin: 18px 0 0;
}

.layout {
    display: grid;
    grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.9fr);
    gap: 18px;
    padding: 18px 0 56px;
}

.panel {
    border: 1px solid var(--line);
    border-radius: 24px;
    padding: 24px;
    background: var(--card);
}

.panel h2 {
    margin: 0 0 16px;
    font-size: 1.2rem;
}

.preview-grid {
    display: grid;
    gap: 18px;
}

.facts {
    display: grid;
    gap: 12px;
}

.fact-label {
    display: block;
    color: var(--muted);
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 3px;
}

.button-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 18px;
}

.tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
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

.button-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 14px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: white;
    color: var(--ink);
    font-size: 0.95rem;
}

.button-link.primary {
    border-color: rgba(15, 118, 110, 0.18);
    background: rgba(15, 118, 110, 0.1);
    color: var(--accent);
}

.table-meta {
    color: var(--muted);
    font-size: 0.95rem;
}

@media (max-width: 860px) {
    .layout {
        grid-template-columns: 1fr;
    }
}
</style>

<style scoped>
.hero {
    padding: 24px 0;
}

.eyebrow {
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.82rem;
    margin: 0 0 10px;
}

h1 {
    margin: 0;
    font-size: clamp(2.6rem, 6vw, 4.6rem);
    line-height: 0.98;
}

.lead {
    color: var(--muted);
    max-width: 62ch;
    line-height: 1.7;
    margin: 18px 0 0;
}

.layout {
    display: grid;
    grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.9fr);
    gap: 18px;
    padding: 18px 0 56px;
}

.panel {
    border: 1px solid var(--line);
    border-radius: 24px;
    padding: 24px;
    background: var(--card);
}

.panel h2 {
    margin: 0 0 16px;
    font-size: 1.2rem;
}

.facts {
    display: grid;
    gap: 12px;
}

.fact-label {
    display: block;
    color: var(--muted);
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 3px;
}

.button-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 18px;
}

.tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
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

.button-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 14px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: white;
    color: var(--ink);
    font-size: 0.95rem;
}

.button-link.primary {
    border-color: rgba(15, 118, 110, 0.18);
    background: rgba(15, 118, 110, 0.1);
    color: var(--accent);
}

.tables {
    display: grid;
    gap: 12px;
}

.table-card {
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.54);
}

.table-title {
    font-weight: 700;
    margin-bottom: 6px;
}

.table-meta {
    color: var(--muted);
    font-size: 0.95rem;
}

.table-links {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 12px;
}

@media (max-width: 860px) {
    .layout {
        grid-template-columns: 1fr;
    }
}
</style>