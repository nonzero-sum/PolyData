<template>
    <div class="map-preview">
        <header class="preview-header">
            <h3>Map preview</h3>
            <p v-if="bounds" class="preview-subtitle">Auto-zoom to resource bounds</p>
        </header>

        <div ref="mapContainer" class="map-container" />
        <div v-if="error" class="preview-error">{{ error }}</div>
    </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

const props = defineProps({
    collectionUrl: {
        type: String,
        required: true,
    },
    bounds: {
        type: Array,
        default: null,
    },
    maxFeatures: {
        type: Number,
        default: 500,
    },
})

const mapContainer = ref(null)
const error = ref(null)

let mapInstance = null

function getFeatureType(features) {
    if (!Array.isArray(features) || features.length === 0) {
        return null
    }

    const geometry = features[0] && features[0].geometry
    return geometry ? geometry.type : null
}

function createLayerConfig(geometryType) {
    if (geometryType === 'Point' || geometryType === 'MultiPoint') {
        return {
            id: 'resource-data-layer',
            type: 'circle',
            source: 'resource-data',
            paint: {
                'circle-radius': 6,
                'circle-color': '#007acc',
                'circle-stroke-color': '#ffffff',
                'circle-stroke-width': 1.5,
            },
        }
    }

    if (geometryType === 'LineString' || geometryType === 'MultiLineString') {
        return {
            id: 'resource-data-layer',
            type: 'line',
            source: 'resource-data',
            paint: {
                'line-color': '#007acc',
                'line-width': 2,
            },
        }
    }

    return {
        id: 'resource-data-layer',
        type: 'fill',
        source: 'resource-data',
        paint: {
            'fill-color': '#007acc',
            'fill-opacity': 0.3,
            'fill-outline-color': '#005a99',
        },
    }
}

function appendCoordinates(geometry, result) {
    if (!geometry || !geometry.type) {
        return
    }

    if (geometry.type === 'GeometryCollection') {
        const geometries = Array.isArray(geometry.geometries) ? geometry.geometries : []
        for (const childGeometry of geometries) {
            appendCoordinates(childGeometry, result)
        }
        return
    }

    appendNestedCoordinates(geometry.coordinates, result)
}

function appendNestedCoordinates(value, result) {
    if (!Array.isArray(value)) {
        return
    }

    if (typeof value[0] === 'number' && typeof value[1] === 'number') {
        result.push([value[0], value[1]])
        return
    }

    for (const childValue of value) {
        appendNestedCoordinates(childValue, result)
    }
}

function computeGeojsonBoundingBox(geojson) {
    if (!geojson || !Array.isArray(geojson.features)) {
        return null
    }

    const coordinates = []
    for (const feature of geojson.features) {
        appendCoordinates(feature && feature.geometry, coordinates)
    }

    if (coordinates.length === 0) {
        return null
    }

    let minX = coordinates[0][0]
    let minY = coordinates[0][1]
    let maxX = coordinates[0][0]
    let maxY = coordinates[0][1]

    for (const coordinate of coordinates) {
        const x = coordinate[0]
        const y = coordinate[1]

        if (x < minX) minX = x
        if (y < minY) minY = y
        if (x > maxX) maxX = x
        if (y > maxY) maxY = y
    }

    return [minX, minY, maxX, maxY]
}

function fitMapToData(geojson) {
    if (!mapInstance) {
        return
    }

    if (Array.isArray(props.bounds) && props.bounds.length === 4) {
        mapInstance.fitBounds(props.bounds, { padding: 40, duration: 0 })
        return
    }

    if (Array.isArray(geojson.bbox) && geojson.bbox.length === 4) {
        mapInstance.fitBounds(geojson.bbox, { padding: 40, duration: 0 })
        return
    }

    const computedBounds = computeGeojsonBoundingBox(geojson)
    if (computedBounds) {
        mapInstance.fitBounds(computedBounds, { padding: 40, duration: 0 })
    }
}

function buildItemsUrl() {
    const normalizedUrl = props.collectionUrl.endsWith('/') ? props.collectionUrl : `${props.collectionUrl}/`
    const url = new URL(`${normalizedUrl}items/`)
    url.searchParams.set('f', 'json')
    url.searchParams.set('limit', String(props.maxFeatures))
    return url.toString()
}

async function loadGeojson() {
    if (!mapInstance) {
        return
    }

    try {
        error.value = null

        const response = await fetch(buildItemsUrl())
        if (!response.ok) {
            throw new Error(`Unable to load GeoJSON (${response.status})`)
        }

        const geojson = await response.json()
        const source = mapInstance.getSource('resource-data')

        if (source) {
            source.setData(geojson)
        } else {
            mapInstance.addSource('resource-data', {
                type: 'geojson',
                data: geojson,
            })

            mapInstance.addLayer(createLayerConfig(getFeatureType(geojson.features)))
        }

        fitMapToData(geojson)
    } catch (err) {
        error.value = err instanceof Error ? err.message : String(err)
    }
}

function setUpMap() {
    if (!mapContainer.value) {
        return
    }

    mapInstance = new maplibregl.Map({
        container: mapContainer.value,
        style: 'https://demotiles.maplibre.org/style.json',
        center: [0, 0],
        zoom: 2,
    })

    mapInstance.addControl(
        new maplibregl.NavigationControl({ showCompass: true, showZoom: true }),
        'top-right'
    )

    mapInstance.on('load', loadGeojson)
}

onMounted(() => {
    if (typeof window === 'undefined') {
        return
    }

    setUpMap()
})

onBeforeUnmount(() => {
    if (!mapInstance) {
        return
    }

    mapInstance.remove()
    mapInstance = null
})

watch(() => props.collectionUrl, () => {
    if (!mapInstance) {
        return
    }

    loadGeojson()
})
</script>

<style scoped>
.map-preview {
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.54);
}

.preview-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 12px;
}

.preview-header h3 {
    margin: 0;
    font-size: 1.1rem;
}

.preview-subtitle {
    font-size: 0.9rem;
    color: var(--muted);
    margin: 0;
}

.map-container {
    width: 100%;
    height: 360px;
    border-radius: 16px;
    overflow: hidden;
}

.preview-error {
    margin-top: 10px;
    color: var(--danger);
}
</style>