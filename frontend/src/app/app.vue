<template>
  <div class="shell">
    <header class="header">
      <NuxtLink class="brand" to="/">PolyData</NuxtLink>
      <nav class="nav" aria-label="Primary navigation">
        <NuxtLink to="/datasets/">Datasets</NuxtLink>
        <NuxtLink to="/resources/">Resources</NuxtLink>
        <NuxtLink to="/organizations/">Organizations</NuxtLink>
        <a :href="swaggerUrl">API</a>
        <a :href="loginUrl">Log in</a>
      </nav>
    </header>
    <NuxtRouteAnnouncer />
    <NuxtPage />
  </div>
</template>

<script setup>
const config = useRuntimeConfig()
const backendBaseUrl = computed(() => (config.public.backendUrl || 'http://localhost:8000').replace(/\/$/, ''))
const swaggerUrl = computed(() => `${backendBaseUrl.value}/api/schema/swagger-ui/`)
const loginUrl = computed(() => `${backendBaseUrl.value}/dms/`)
</script>

<style>
:root {
  --paper: #f7f1e8;
  --ink: #1f2a2a;
  --muted: #5b6765;
  --accent: #0f766e;
  --accent-dark: #0a4f4a;
  --line: rgba(31, 42, 42, 0.12);
  --card: rgba(255, 252, 247, 0.84);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.16), transparent 28%),
    radial-gradient(circle at 85% 15%, rgba(234, 179, 8, 0.16), transparent 24%),
    linear-gradient(180deg, #fbf6ef 0%, var(--paper) 100%);
}

a {
  color: inherit;
  text-decoration: none;
}

.shell {
  width: min(1120px, calc(100vw - 32px));
  margin: 0 auto;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 0;
}

.brand {
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.nav {
  display: flex;
  gap: 18px;
  align-items: center;
}

.nav a {
  padding: 10px 14px;
  border-radius: 999px;
  color: var(--muted);
}

.nav a:hover {
  color: var(--ink);
  background: rgba(255, 255, 255, 0.5);
}
</style>
