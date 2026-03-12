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
                <h2>Tables</h2>
                <div v-if="resource.tables?.length" class="tables">
                    <div v-for="table in resource.tables" :key="table.id" class="table-card">
                        <div class="table-title">{{ table.layer_name || table.table_name }}</div>
                        <div class="table-meta">
                            {{ table.qualified_table_name }}<span v-if="table.is_primary"> | primary</span>
                        </div>
                        <div class="table-meta">
                            Rows: {{ table.row_count }}<span v-if="table.geometry_field"> | Geometry: {{
                                table.geometry_field }}</span>
                        </div>
                        <div class="table-links">
                            <a v-if="table.table_url" class="button-link" :href="table.table_url">table_url</a>
                            <a v-if="table.rows_url" class="button-link" :href="table.rows_url">rows_url</a>
                            <a v-if="table.ogc_collection_url" class="button-link primary"
                                :href="table.ogc_collection_url">ogc_collection_url</a>
                        </div>
                    </div>
                </div>
                <div v-else class="table-meta">This resource has no derived tables yet.</div>
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
import { ref, watch } from 'vue'

const resource = ref(null)
const route = useRoute()
const apiBaseUrl = useApiBaseUrl()

function formatLabel(value) {
    if (!value) return 'Unknown'
    return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

async function fetchResource() {
    const res = await fetch(`${apiBaseUrl}/resources/${route.params.id}/`)
    resource.value = res.ok ? await res.json() : null
}

await fetchResource()
watch(() => route.params.id, fetchResource)
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