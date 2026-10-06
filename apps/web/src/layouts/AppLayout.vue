<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { api, clearSession, user } from '../api/client';
import { openSearch } from '../composables/ui';
import SearchDialog from '../components/SearchDialog.vue';
import EvidenceDrawer from '../components/EvidenceDrawer.vue';

const router = useRouter();
const route = useRoute();
const drawer = ref(false);
const online = ref(navigator.onLine);
const links = [
  { to: '/', label: 'Timeline', icon: 'timeline' },
  { to: '/library', label: 'My library', icon: 'auto_stories' },
  { to: '/review', label: 'Review queue', icon: 'fact_check' },
  { to: '/sources', label: 'Sources', icon: 'sensors' },
  { to: '/settings', label: 'Settings', icon: 'tune' },
];
const connection = () => { online.value = navigator.onLine; };
const shortcut = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key === 'k') { event.preventDefault(); openSearch(); } };
async function logout() { try { await api('/auth/logout', { method: 'POST' }); } finally { clearSession(); await router.replace('/login'); } }
onMounted(() => { window.addEventListener('online', connection); window.addEventListener('offline', connection); window.addEventListener('keydown', shortcut); });
onUnmounted(() => { window.removeEventListener('online', connection); window.removeEventListener('offline', connection); window.removeEventListener('keydown', shortcut); });
</script>

<template>
  <q-layout view="hHh Lpr lFf" class="app-shell">
    <q-header v-if="$q.screen.width <= 900" class="mobile-header" bordered><q-toolbar><q-btn flat round icon="menu" aria-label="Open navigation" @click="drawer = !drawer" /><span class="brand-mini">Release<span>Holic</span></span><q-space /><q-btn flat round icon="search" aria-label="Find a story" @click="openSearch()" /></q-toolbar></q-header>
    <q-drawer v-model="drawer" show-if-above :width="224" :breakpoint="900" class="sidebar">
      <router-link to="/" class="brand"><span class="brand-mark"><q-icon name="all_inclusive" /></span><span>Release<span class="brand-light">Holic</span><small>FOLLOW THE STORY</small></span></router-link>
      <div class="sidebar-caption">YOUR SPACE</div>
      <nav aria-label="Main navigation" class="nav-list"><router-link v-for="link in links" :key="link.to" :to="link.to" :class="['nav-item', { active: route.path === link.to }]" @click="drawer = false"><q-icon :name="link.icon" size="21px" /><span>{{ link.label }}</span><span v-if="route.path === link.to" class="nav-dot" /></router-link></nav>
      <div class="sidebar-note"><div class="note-symbol">✦</div><strong>Every story has a next chapter.</strong><p>Keep the premieres, updates, and possibilities together.</p><q-btn unelevated color="primary" label="Find a story" icon="add" no-caps @click="openSearch()" /></div>
      <div class="sidebar-user"><q-avatar size="34px" class="user-avatar">{{ user?.username.slice(0, 1).toUpperCase() }}</q-avatar><div><strong>{{ user?.username }}</strong><small>Personal library</small></div><q-btn flat round size="sm" icon="logout" aria-label="Sign out" @click="logout" /></div>
    </q-drawer>
    <q-page-container>
      <div v-if="!online" class="offline-banner" role="status"><q-icon name="wifi_off" /> You’re offline. Previously loaded views are available; changes resume when you reconnect.</div>
      <router-view />
    </q-page-container>
    <SearchDialog /><EvidenceDrawer />
  </q-layout>
</template>
