<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import type { ComponentPublicInstance } from 'vue';
import { useVirtualizer } from '@tanstack/vue-virtual';
import { api, json, queryString } from '../api/client';
import type { EventOut, FilterOut, FranchiseOut, StatsOut, TimelineOut } from '../api/contracts';
import { displayTimezone, localToday, openSearch, report, success } from '../composables/ui';
import PageHeading from '../components/PageHeading.vue';
import EventCard from '../components/EventCard.vue';

const defaults = () => ({ medium: '', kind: '', platform: '', region: '', verification: '', lifecycle: '', franchise_id: '', work_id: '', status: '', library_only: true, date_from: localToday(), date_to: '', basis: 'release' });
const filters = reactive(defaults());
const events = ref<EventOut[]>([]), undated = ref<EventOut[]>([]);
const total = ref(0), tbaCount = ref(0), loading = ref(true), loadingMore = ref(false), error = ref('');
const stats = ref<StatsOut | null>(null), saved = ref<FilterOut[]>([]), selectedView = ref<string | null>(null);
const franchises = ref<FranchiseOut[]>([]);
const filterOpen = ref(false), saveOpen = ref(false), viewName = ref(''), period = ref('upcoming');
const scroll = ref<HTMLElement | null>(null);
let generation = 0, debounce: ReturnType<typeof setTimeout> | undefined;
const mediums = [{ label: 'All media', value: '' }, { label: 'TV shows', value: 'show' }, { label: 'Movies', value: 'movie' }, { label: 'Anime', value: 'anime' }, { label: 'Web novels', value: 'web_novel' }, { label: 'Light novels', value: 'light_novel' }];
const kinds = [{ label: 'Everything', value: '' }, { label: 'Releases', value: 'releases' }, { label: 'Announcements', value: 'announcement' }, { label: 'Trailers & PVs', value: 'pv' }, { label: 'Rumours', value: 'rumour' }, { label: 'Availability', value: 'availability' }, { label: 'Sequels', value: 'sequel' }, { label: 'Adaptations', value: 'adaptation' }, { label: 'Delays', value: 'delay' }, { label: 'Metadata changes', value: 'metadata_change' }];
const trust = [{ label: 'Any verification', value: '' }, ...['confirmed', 'reported', 'unverified', 'contradicted', 'retracted'].map(value => ({ label: value[0]!.toUpperCase() + value.slice(1), value }))];
const progressOptions = [{ label: 'All reading / watching states', value: '' }, ...['planned', 'in_progress', 'completed', 'paused', 'dropped'].map(value => ({ label: value.replace('_', ' '), value }))];
function groupLabel(event: EventOut) {
  if (filters.basis === 'announcement' || event.precision === 'instant') {
    const timestamp = filters.basis === 'announcement' ? event.published_at || event.observed_at : event.scheduled_at;
    if (timestamp) return new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' }).format(new Date(timestamp));
  }
  const value = filters.basis === 'announcement' ? (event.published_at || event.observed_at).slice(0, 10) : event.window_start;
  if (!value) return 'Date to be announced';
  // A year-wide or seasonal window must never look like a January/day release.
  if (filters.basis === 'release' && ['year', 'season'].includes(event.precision)) return event.date_label || value.slice(0, 4);
  return new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' }).format(new Date(value.slice(0, 7) + '-15T12:00:00'));
}
const rows = computed(() => events.value.map((event, index) => ({ event, heading: index === 0 || groupLabel(events.value[index - 1]!) !== groupLabel(event) ? groupLabel(event) : '' })));
const virtualizer = useVirtualizer(computed(() => ({ count: rows.value.length, getScrollElement: () => scroll.value, estimateSize: (index: number) => rows.value[index]?.heading ? 204 : 162, overscan: 6, getItemKey: (index: number) => rows.value[index]!.event.id })));
const virtualRows = computed(() => virtualizer.value.getVirtualItems());
function measureRow(node: Element | ComponentPublicInstance | null) {
  virtualizer.value.measureElement(node instanceof Element ? node : null);
}
watch(virtualRows, items => { const last = items.at(-1); if (last && last.index >= rows.value.length - 6 && events.value.length < total.value) void loadMore(); });
const activeFilterCount = computed(() => [filters.medium, filters.platform, filters.region, filters.verification, filters.lifecycle, filters.status, filters.franchise_id, filters.work_id, filters.date_to].filter(Boolean).length);

async function reload() {
  const current = ++generation;
  loading.value = true; error.value = ''; events.value = [];
  const snapshot = { ...filters, display_timezone: displayTimezone() };
  try {
    const [timeline, tba, counts] = await Promise.all([
      api<TimelineOut>('/timeline?' + queryString({ ...snapshot, include_tba: false, limit: 60 })),
      api<TimelineOut>('/timeline?' + queryString({ ...snapshot, basis: 'release', date_from: '', date_to: '', tba_only: true, limit: 8 })),
      api<StatsOut>('/stats?' + queryString({ display_timezone: displayTimezone() })),
    ]);
    if (current !== generation) return;
    events.value = timeline.events; total.value = timeline.total; undated.value = tba.events; tbaCount.value = tba.total; stats.value = counts;
    scroll.value?.scrollTo({ top: 0 });
  } catch (err) { if (current === generation) error.value = err instanceof Error ? err.message : 'Could not load your timeline.'; }
  finally { if (current === generation) loading.value = false; }
}
async function loadMore() {
  if (loading.value || loadingMore.value || events.value.length >= total.value) return;
  const current = generation;
  loadingMore.value = true;
  try {
    const result = await api<TimelineOut>('/timeline?' + queryString({ ...filters, display_timezone: displayTimezone(), include_tba: false, offset: events.value.length, limit: 60 }));
    if (current === generation) { events.value.push(...result.events); total.value = result.total; }
  } catch (err) { report(err); }
  finally { loadingMore.value = false; }
}
function switchPeriod(value: string) { period.value = value; filters.date_from = value === 'upcoming' ? localToday() : ''; filters.date_to = value === 'history' ? localToday() : ''; }
async function saveView() {
  try { const result = await api<FilterOut>('/filters', json({ name: viewName.value.trim(), filters: { ...filters } })); saved.value.push(result); selectedView.value = result.id; saveOpen.value = false; viewName.value = ''; success('View saved'); }
  catch (err) { report(err); }
}
function applyView(id: string | null) {
  const view = saved.value.find(item => item.id === id);
  if (view) { Object.assign(filters, defaults(), view.filters); period.value = 'custom'; }
}
async function deleteView() { if (!selectedView.value) return; try { await api(`/filters/${selectedView.value}`, { method: 'DELETE' }); saved.value = saved.value.filter(row => row.id !== selectedView.value); selectedView.value = null; } catch (err) { report(err); } }
watch(filters, () => { clearTimeout(debounce); debounce = setTimeout(() => void reload(), 180); }, { deep: true });
const changed = () => void reload();
onMounted(() => { void reload(); void api<FilterOut[]>('/filters').then(result => { saved.value = result; }).catch(report); void api<FranchiseOut[]>('/franchises').then(result => { franchises.value = result; }).catch(report); window.addEventListener('catalogue-updated', changed); });
onUnmounted(() => { generation++; clearTimeout(debounce); window.removeEventListener('catalogue-updated', changed); });
</script>

<template>
  <q-page class="page timeline-page">
    <PageHeading title="Your next chapter" subtitle="Every release, announcement, and possibility. One timeline."><q-btn outline no-caps icon="bookmark_border" label="Save view" @click="saveOpen = true" /><q-btn unelevated color="primary" no-caps icon="add" label="Follow a story" @click="openSearch()" /></PageHeading>
    <div class="summary-strip"><div><span class="summary-icon purple"><q-icon name="auto_stories" /></span><span><strong>{{ stats?.followed ?? '—' }}</strong><small>Stories followed</small></span></div><div><span class="summary-icon green"><q-icon name="event_available" /></span><span><strong>{{ stats?.upcoming ?? '—' }}</strong><small>Upcoming events</small></span></div><router-link to="/review"><span class="summary-icon amber"><q-icon name="fact_check" /></span><span><strong>{{ stats?.needs_review ?? '—' }}</strong><small>Waiting for review</small></span><q-icon name="arrow_outward" class="summary-arrow" /></router-link><div class="summary-note"><span class="live-dot" /> Monitoring continues while you’re away</div></div>
    <div class="timeline-toolbar"><div class="segmented-control" aria-label="Timeline period"><button :class="{ selected: period === 'upcoming' }" @click="switchPeriod('upcoming')">Upcoming</button><button :class="{ selected: period === 'history' }" @click="switchPeriod('history')">History</button><button :class="{ selected: period === 'all' }" @click="switchPeriod('all')">All time</button></div><q-space /><q-select v-if="saved.length" v-model="selectedView" :options="saved.map(item => ({ label: item.name, value: item.id }))" emit-value map-options clearable dense borderless label="Saved views" class="saved-view-select" @update:model-value="applyView" /><q-btn v-if="selectedView" flat round size="sm" icon="delete_outline" aria-label="Delete saved view" @click="deleteView" /><q-btn flat no-caps icon="tune" :label="`Filters${activeFilterCount ? ' · ' + activeFilterCount : ''}`" :class="{ 'filter-active': activeFilterCount || filterOpen }" @click="filterOpen = !filterOpen" /></div>
    <div class="event-tabs"><button v-for="item in kinds.slice(0, 6)" :key="item.value" :class="{ selected: filters.kind === item.value }" @click="filters.kind = item.value">{{ item.label }}</button></div>
    <div v-if="filterOpen" class="filter-panel"><q-select v-model="filters.medium" :options="mediums" emit-value map-options outlined dense label="Medium" /><q-select v-model="filters.kind" :options="kinds" emit-value map-options outlined dense label="Event type" /><q-input v-model="filters.platform" outlined dense label="Platform" placeholder="Netflix, Apple TV…" /><q-input v-model="filters.region" outlined dense label="Country code" placeholder="JP, US…" maxlength="10" /><q-select v-model="filters.verification" :options="trust" emit-value map-options outlined dense label="Verification" /><q-select v-model="filters.status" :options="progressOptions" emit-value map-options outlined dense label="Progress" /><q-select v-model="filters.basis" :options="[{ label: 'Release / event date', value: 'release' }, { label: 'Published / observed date', value: 'announcement' }]" emit-value map-options outlined dense label="Date basis" /><q-input v-model="filters.date_from" type="date" outlined dense label="From" /><q-input v-model="filters.date_to" type="date" outlined dense label="Through" /><q-select v-model="filters.franchise_id" :options="[{ label: 'All franchises', value: '' }, ...franchises.map(item => ({ label: item.title, value: item.id }))]" emit-value map-options outlined dense label="Franchise" /><q-select v-model="filters.lifecycle" :options="[{ label: 'Any lifecycle', value: '' }, ...['announced', 'scheduled', 'released', 'delayed', 'cancelled'].map(value => ({ label: value, value }))]" emit-value map-options outlined dense label="Lifecycle" /><q-checkbox v-model="filters.library_only" label="Only stories I follow" /><q-btn flat no-caps label="Reset filters" @click="Object.assign(filters, defaults()); period = 'upcoming'; selectedView = null" /></div>
    <div v-if="error" class="error-panel" role="alert"><q-icon name="cloud_off" /><p>{{ error }}</p><q-btn outline no-caps label="Try again" @click="reload" /></div>
    <div v-else class="timeline-columns">
      <section class="timeline-main" aria-label="Dated timeline"><div class="section-caption"><span>{{ filters.basis === 'announcement' ? 'WHEN THE NEWS ARRIVED' : 'ON THE HORIZON' }}</span><span>{{ total }} event{{ total === 1 ? '' : 's' }}</span></div>
        <div v-if="loading" class="skeleton-list" aria-label="Loading timeline"><q-skeleton v-for="n in 3" :key="n" height="146px" class="rounded-panel" /></div>
        <div v-else-if="!events.length" class="empty-state"><span class="empty-symbol"><q-icon name="explore" /></span><h2>{{ stats?.followed ? 'A quiet stretch ahead' : 'A story starts with a follow' }}</h2><p>{{ stats?.followed ? 'Try another date range or check the undated releases. Your sources will keep looking for updates.' : 'Find a show, film, anime, or novel. Its releases and source evidence will find a home here.' }}</p><q-btn unelevated color="primary" no-caps label="Find a story" icon="add" @click="openSearch()" /></div>
        <div v-else ref="scroll" class="timeline-scroll" tabindex="0" aria-label="Scrollable timeline"><div :style="{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }"><div v-for="row in virtualRows" :key="String(row.key)" :ref="measureRow" :data-index="row.index" class="virtual-row" :style="{ position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${row.start}px)` }"><div v-if="rows[row.index]?.heading" class="timeline-group"><span class="timeline-point" /><h2>{{ rows[row.index]?.heading }}</h2></div><EventCard :event="rows[row.index]!.event" :basis="filters.basis" /></div></div><div class="list-end"><q-spinner v-if="loadingMore" color="primary" /><q-btn v-else-if="events.length < total" flat no-caps label="Load more" @click="loadMore" /><span v-else>You’re all caught up with this view.</span></div></div>
      </section>
      <aside class="tba-aside"><div class="section-caption"><span>STILL A POSSIBILITY</span><span>{{ tbaCount }}</span></div><div class="tba-intro"><span class="tba-spark">✧</span><h2>Dates to be announced</h2><p>Confirmed plans and early signals, waiting for a place on the calendar.</p></div><q-skeleton v-if="loading" height="120px" /><template v-else><EventCard v-for="event in undated" :key="event.id" :event="event" compact /><div v-if="!undated.length" class="tba-empty">No undated events in this view.</div><p v-if="tbaCount > undated.length" class="muted">Showing {{ undated.length }} of {{ tbaCount }}. Narrow the filters to find a story.</p></template><div class="source-note"><q-icon name="verified_user" /><div><strong>Follow the evidence</strong><p>Open any event to see its source, precision, and revision history.</p></div></div></aside>
    </div>
    <q-dialog v-model="saveOpen"><q-card class="small-dialog"><q-form @submit="saveView"><q-card-section><h2>Save this view</h2><p class="muted">Keep this set of filters for next time.</p><q-input v-model="viewName" autofocus outlined label="View name" maxlength="100" :rules="[value => !!String(value).trim() || 'Enter a name']" /></q-card-section><q-card-actions align="right"><q-btn flat no-caps label="Cancel" v-close-popup /><q-btn unelevated color="primary" no-caps label="Save view" type="submit" /></q-card-actions></q-form></q-card></q-dialog>
  </q-page>
</template>
