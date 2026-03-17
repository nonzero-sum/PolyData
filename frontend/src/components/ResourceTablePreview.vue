<template>
  <div class="table-preview">
    <header class="preview-header">
      <h3>Table preview</h3>
      <p class="preview-subtitle" v-if="rowCount !== null">Showing {{ rows.length }} of {{ rowCount }} rows</p>
    </header>

    <div v-if="loading" class="preview-loading">Loading rows…</div>
    <div v-else-if="error" class="preview-error">{{ error }}</div>
    <div v-else>
      <div v-if="rows.length">
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th v-for="column in columns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
                <td v-for="column in columns" :key="column">
                  <code>{{ formatCell(row[column]) }}</code>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else class="preview-empty">No rows returned.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'

const props = defineProps({
  rowsUrl: {
    type: String,
    required: true,
  },
  pageSize: {
    type: Number,
    default: 10,
  },
})

const rows = ref([])
const columns = ref([])
const rowCount = ref(null)
const loading = ref(false)
const error = ref(null)

async function loadRows() {
  loading.value = true
  error.value = null

  try {
    const url = new URL(props.rowsUrl, window.location.origin)
    url.searchParams.set('page_size', String(props.pageSize))

    const res = await fetch(url.toString())
    if (!res.ok) {
      throw new Error(`Failed to load rows (status ${res.status})`)
    }

    const json = await res.json()
    rowCount.value = typeof json.count === 'number' ? json.count : null
    rows.value = Array.isArray(json.results) ? json.results : []
    columns.value = rows.value.length > 0 ? Object.keys(rows.value[0]) : []
  } catch (err) {
    error.value = err.message || String(err)
  } finally {
    loading.value = false
  }
}

function formatCell(value) {
  if (value === null || value === undefined) return ''

  // Render small objects nicely
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }

  return String(value)
}

onMounted(loadRows)
watch(() => props.rowsUrl, loadRows)
</script>

<style scoped>
.table-preview {
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

.table-scroll {
  overflow-x: auto;
  max-width: 100%;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

th,
 td {
  border: 1px solid var(--line);
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
}

th {
  background: rgba(15, 118, 110, 0.08);
  color: var(--accent);
}

.preview-loading,
.preview-error,
.preview-empty {
  color: var(--muted);
  font-size: 0.95rem;
  padding: 12px 0;
}

.preview-error {
  color: var(--danger);
}
</style>
