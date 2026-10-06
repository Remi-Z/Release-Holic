<script setup lang="ts">
import type { EventOut } from '../api/contracts';
import { eventLabel, mediaLabel, releaseLabel, selectedEvent, timestampLabel } from '../composables/ui';
defineProps<{ event: EventOut; compact?: boolean; basis?: string }>();
</script>
<template>
  <button type="button" :class="['event-card', event.work_kind, { compact }]" @click="selectedEvent = event">
    <span class="event-art" aria-hidden="true"><q-icon :name="event.kind === 'pv' ? 'play_arrow' : event.work_kind === 'web_novel' || event.work_kind === 'light_novel' ? 'menu_book' : event.work_kind === 'anime' ? 'auto_awesome' : event.work_kind === 'movie' ? 'movie' : 'live_tv'" /></span>
    <span class="event-content"><span class="event-topline"><span v-if="event.provider === 'demo'" class="demo-event-label">Fictional demo</span><span class="media-text">{{ mediaLabel(event.work_kind) }}</span><span>·</span><span>{{ eventLabel(event.kind) }}</span><span v-if="event.platform">· {{ event.platform }}</span></span><span class="event-work">{{ event.work_title }}</span><span class="event-title">{{ event.title }}</span><span v-if="!compact && event.summary" class="event-summary">{{ event.summary }}</span><span class="event-footer"><span v-if="event.region">{{ event.region }}<span class="footer-dot">·</span></span><span>{{ event.provider }}</span><span class="footer-dot">·</span><q-icon name="link" size="13px" /><span>{{ event.evidence_count }} source{{ event.evidence_count === 1 ? '' : 's' }}</span><span v-if="event.personal" class="personal-mark">Personal</span></span></span>
    <span class="event-status"><span :class="['trust-badge', event.verification]">{{ event.verification === 'unverified' ? 'Unverified' : event.verification === 'confirmed' ? 'Confirmed' : event.verification === 'reported' ? 'Reported' : event.verification }}</span><span class="event-date">{{ basis === 'announcement' ? timestampLabel(event.published_at || event.observed_at) : releaseLabel(event) }}<small v-if="basis === 'announcement' && !event.published_at"> (observed)</small></span><span v-if="['delayed', 'cancelled'].includes(event.lifecycle)" class="lifecycle-label">{{ event.lifecycle }}</span><q-icon name="arrow_outward" class="event-arrow" /></span>
  </button>
</template>
