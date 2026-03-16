<template>
    <div v-if="dataset">
        <section class="hero">
            <p class="eyebrow">Dataset Detail</p>
            <h1>{{ dataset.title }}</h1>
            <p class="lead">{{ dataset.description || 'No description yet.' }}</p>
        </section>

        <section class="layout">
            <div class="panel">
                <h2>Resources</h2>
                <div v-if="dataset.resources?.length" class="resources">
                    <div v-for="resource in dataset.resources" :key="resource.id" class="resource">
                        <div class="resource-title">{{ resource.title }}</div>
                        <div class="resource-meta">{{ formatLabel(resource.resource_kind) }}</div>
                        <div v-if="resource.description" class="resource-meta">{{ resource.description }}</div>
                        <div class="resource-actions">
                            <NuxtLink class="button-link" :to="`/resources/${resource.id}`">View details</NuxtLink>
                            <a v-if="resource.file_representation?.download_url" class="button-link primary"
                                :href="resource.file_representation.download_url">Download</a>
                        </div>
                    </div>
                </div>
                <div v-else class="resource-meta">This dataset has no public resources.</div>
            </div>

            <aside class="panel">
                <h2>Metadata</h2>
                <div class="metadata-sections">
                    <section>
                        <p class="section-label">Catalog</p>
                        <div class="facts-grid">
                            <div class="fact-card">
                                <span class="fact-label">Organization</span>
                                <NuxtLink v-if="dataset.organization" :to="`/organizations/${dataset.organization.id}`">
                                    {{ dataset.organization.title }}
                                </NuxtLink>
                                <span v-else>Not assigned</span>
                            </div>
                            <div class="fact-card">
                                <span class="fact-label">License</span>
                                <span>{{ dataset.license?.title || 'Not assigned' }}</span>
                            </div>
                            <div class="fact-card">
                                <span class="fact-label">Update Frequency</span>
                                <span>{{ formatLabel(dataset.update_frequency) }}</span>
                            </div>
                            <div class="fact-card">
                                <span class="fact-label">Identificador</span>
                                <span>{{ dataset.metadata?.identifier || dataset.slug }}</span>
                            </div>
                        </div>
                    </section>

                    <section>
                        <p class="section-label">Dublin Core</p>
                        <div class="facts-grid">
                            <div v-for="fact in detailFacts" :key="fact.label" class="fact-card"
                                :class="{ 'fact-card-wide': fact.wide }">
                                <span class="fact-label">{{ fact.label }}</span>
                                <span>{{ fact.value }}</span>
                            </div>
                        </div>
                    </section>
                </div>
            </aside>
        </section>
    </div>

    <p v-else>Loading...</p>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const dataset = ref(null)
const route = useRoute()
const apiBaseUrl = useApiBaseUrl()

const dateTimeFormatter = new Intl.DateTimeFormat('es-MX', {
    dateStyle: 'long',
    timeStyle: 'short',
})

function formatLabel(value) {
    if (!value) return 'Unknown'
    return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function formatDateTime(value) {
    if (!value) return 'No disponible'

    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) {
        return 'No disponible'
    }

    return dateTimeFormatter.format(parsed)
}

function formatMetadataDate(value) {
    if (!value) return 'No definida'
    return formatDateTime(value)
}

const detailFacts = computed(() => {
    if (!dataset.value) return []

    const fields = dataset.value.metadata || {}
    const subjectValue = Array.isArray(fields.subject) ? fields.subject.join(', ') : fields.subject
    const rightsValue = fields.rights?.title || fields.rights?.code
    const items = [
        { label: 'Título', value: fields.title || dataset.value.title, wide: true },
        { label: 'Identificador', value: fields.identifier || dataset.value.slug, wide: true },
        { label: 'Tema', value: subjectValue, wide: true },
        { label: 'Descripción', value: fields.description || dataset.value.description, wide: true },
        { label: 'Fuente', value: fields.source, wide: true },
        { label: 'Publicación', value: formatMetadataDate(fields.published) },
        { label: 'Tipo', value: fields.type },
        { label: 'Actualización', value: formatMetadataDate(fields.modified) },
        { label: 'Cobertura', value: fields.coverage },
        { label: 'Autor', value: fields.creator },
        { label: 'Editor', value: fields.publisher },
        { label: 'Colaboradores', value: fields.contributor, wide: true },
        { label: 'Derechos', value: rightsValue, wide: true },
        { label: 'Idioma', value: fields.language },
        { label: 'Creación', value: formatMetadataDate(fields.created) },
    ]

    return items.map((item) => ({
        ...item,
        value: item.value || 'No disponible',
    }))
})

async function fetchDataset() {
    const res = await fetch(`${apiBaseUrl}/datasets/${route.params.id}/`)
    dataset.value = res.ok ? await res.json() : null
}

await fetchDataset()
watch(() => route.params.id, fetchDataset)
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
    font-size: clamp(2.8rem, 7vw, 5rem);
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

.metadata-sections {
    display: grid;
    gap: 18px;
}

.section-label {
    margin: 0 0 10px;
    color: var(--muted);
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
}

.facts-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}

.fact-card {
    min-width: 0;
    padding: 14px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.58);
}

.fact-card-wide {
    grid-column: 1 / -1;
}

.fact-label {
    display: block;
    color: var(--muted);
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 3px;
}

.resources {
    display: grid;
    gap: 12px;
}

.resource {
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.54);
}

.resource-title {
    font-weight: 700;
    margin-bottom: 6px;
}

.resource-meta {
    color: var(--muted);
    font-size: 0.95rem;
}

.resource-actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 12px;
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

@media (max-width: 860px) {
    .layout {
        grid-template-columns: 1fr;
    }

    .facts-grid {
        grid-template-columns: 1fr;
    }
}
</style>