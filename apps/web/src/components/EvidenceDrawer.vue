<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../api/client';
import type { EventDetailOut } from '../api/contracts';
import { selectedEvent, report, eventLabel, releaseLabel, timestampLabel } from '../composables/ui';

const open = computed({ get: () => !!selectedEvent.value, set: value => { if (!value) selectedEvent.value = null; } });
const detail = ref<EventDetailOut | null>(null);
const loading = ref(false);
const error = ref('');
watch(selectedEvent, async event => {
  detail.value = null; error.value = '';
  if (!event) return;
  loading.value = true;
  try { const response = await api<EventDetailOut>(`/events/${event.id}`); if (selectedEvent.value?.id === event.id) detail.value = response; }
  catch (e) { error.value = e instanceof Error ? e.message : 'Could not load evidence'; report(e); }
  finally { loading.value = false; }
});
</script>
<template>
  <q-dialog v-model="open" position="right"><q-card class="evidence-panel">
    <div class="panel-heading"><span class="eyebrow">BEHIND THE UPDATE</span><q-btn flat round icon="close" aria-label="Close evidence" v-close-popup /></div>
    <q-linear-progress v-if="loading" indeterminate color="primary" />
    <div v-if="selectedEvent" class="panel-body"><div class="media-text">{{ eventLabel(selectedEvent.kind) }}</div><h2>{{ selectedEvent.work_title }}</h2><p class="panel-title">{{ selectedEvent.title }}</p><div class="detail-dates"><div><small>Release / occurrence</small><strong>{{ releaseLabel(selectedEvent) }}</strong></div><div><small>Verification</small><span :class="['trust-badge', selectedEvent.verification]">{{ selectedEvent.verification }}</span></div></div><p v-if="selectedEvent.summary">{{ selectedEvent.summary }}</p><p v-if="error" role="alert" class="error-text">{{ error }}</p>
      <div v-if="detail"><h3>Source evidence</h3><div v-for="evidence in detail.evidence" :key="evidence.id" class="evidence-item"><div class="eyebrow">{{ evidence.provider }}</div><a :href="evidence.url" target="_blank" rel="noopener noreferrer">{{ evidence.title || evidence.url }} <q-icon name="open_in_new" size="14px" /></a><blockquote v-if="evidence.original_text">{{ evidence.original_text }}</blockquote><dl><dt>Published</dt><dd>{{ timestampLabel(evidence.published_at) }}</dd><dt>Observed</dt><dd>{{ timestampLabel(evidence.observed_at) }}</dd></dl><q-expansion-item v-if="evidence.locator" dense label="Evidence location"><p class="locator">{{ evidence.locator }}</p></q-expansion-item></div><p v-if="!detail.evidence.length" class="muted">No visible source evidence is attached.</p>
        <h3>Revision history</h3><div v-for="revision in detail.revisions" :key="revision.id" class="revision-item"><strong>{{ revision.reason }}</strong><small>{{ timestampLabel(revision.created_at) }}</small><p v-if="revision.before.date_label !== revision.after.date_label">{{ revision.before.date_label || revision.before.window_start || 'TBA' }} <q-icon name="arrow_forward" /> {{ revision.after.date_label || revision.after.window_start || 'TBA' }}</p></div><p v-if="!detail.revisions.length" class="muted">No changes recorded since this update was first observed.</p>
      </div>
      <q-btn flat color="primary" label="View this story" no-caps :to="`/works/${selectedEvent.work_id}`" @click="selectedEvent = null" />
    </div>
  </q-card></q-dialog>
</template>
