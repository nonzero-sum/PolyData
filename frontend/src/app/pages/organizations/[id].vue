<template>
    <div v-if="organization">
        <section class="hero">
            <p class="eyebrow">Organization Detail</p>
            <h1>{{ organization.title }}</h1>
            <p class="lead">{{ organization.description || 'No description yet.' }}</p>
        </section>

        <section class="layout">
            <div class="panel">
                <h2>Datasets</h2>
                <div v-if="organizationDatasets.length" class="datasets">
                    <NuxtLink v-for="dataset in organizationDatasets" :key="dataset.id" class="dataset"
                        :to="`/datasets/${dataset.id}`">
                        <div class="dataset-title">{{ dataset.title }}</div>
                        <div class="dataset-meta">{{ formatLabel(dataset.update_frequency) }}</div>
                        <div v-if="dataset.description" class="dataset-meta">{{ dataset.description }}</div>
                    </NuxtLink>
                </div>
                <div v-else class="dataset-meta">This organization has no public datasets.</div>
            </div>

            <aside class="panel">
                <h2>Details</h2>
                <div class="facts">
                    <div v-if="organization.url"><span class="fact-label">URL</span><a :href="organization.url">{{
                        organization.url }}</a></div>
                    <div v-if="organization.email"><span class="fact-label">Email</span>{{ organization.email }}</div>
                    <div><span class="fact-label">Dataset Count</span>{{ organizationDatasets.length }}</div>
                    <div><span class="fact-label">Slug</span>{{ organization.slug }}</div>
                </div>
            </aside>
        </section>
    </div>

    <p v-else>Loading...</p>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const organization = ref(null)
const datasets = ref([])
const route = useRoute()
const config = useRuntimeConfig()
const organizationDatasets = computed(() => Array.isArray(datasets.value) ? datasets.value : [])

function formatLabel(value) {
    if (!value) return 'Unknown'
    return value.replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

async function fetchOrganization() {
    const base = config.public.backendUrl || 'http://localhost:8000'
    const organizationResponse = await fetch(`${base}/api/organizations/${route.params.id}/`)
    organization.value = organizationResponse.ok ? await organizationResponse.json() : null

    if (!organization.value?.slug) {
        datasets.value = []
        return
    }

    const datasetsUrl = new URL(`${base}/api/datasets/`)
    datasetsUrl.searchParams.set('organization', organization.value.slug)
    const datasetsResponse = await fetch(datasetsUrl.toString())
    if (datasetsResponse.ok) {
        const payload = await datasetsResponse.json()
        datasets.value = payload.results || payload
    } else {
        datasets.value = []
    }
}

await fetchOrganization()
watch(() => route.params.id, fetchOrganization)
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
    grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.9fr);
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
    color: var(--muted);
}

.fact-label {
    display: block;
    color: var(--muted);
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 3px;
}

.datasets {
    display: grid;
    gap: 12px;
}

.dataset {
    display: block;
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.54);
}

.dataset-title {
    font-weight: 700;
    margin-bottom: 6px;
}

.dataset-meta {
    color: var(--muted);
    font-size: 0.95rem;
}

@media (max-width: 860px) {
    .layout {
        grid-template-columns: 1fr;
    }
}
</style>