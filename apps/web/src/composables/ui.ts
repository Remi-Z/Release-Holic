import { ref } from 'vue';
import { Notify } from 'quasar';
import type { EventOut } from '../api/contracts';

export const searchOpen = ref(false);
export const searchPrefill = ref('');
export const selectedEvent = ref<EventOut | null>(null);
export function resetUI() { searchOpen.value = false; searchPrefill.value = ''; selectedEvent.value = null; }
export function report(error: unknown) { Notify.create({ type: 'negative', message: error instanceof Error ? error.message : 'Something went wrong.' }); }
export function success(message: string) { Notify.create({ type: 'positive', message }); }
export function openSearch(value = '') { searchPrefill.value = value; searchOpen.value = true; }
export function mediaLabel(kind: string) { return ({ show: 'TV series', movie: 'Movie', anime: 'Anime', web_novel: 'Web novel', light_novel: 'Light novel' } as Record<string, string>)[kind] || kind; }
export function eventLabel(kind: string) { return ({ announcement: 'Announcement', release: 'Premiere', episode_release: 'Episode', chapter_release: 'Chapter', volume_release: 'Volume', availability: 'Availability', pv: 'PV / trailer', rumour: 'Unverified report', sequel: 'Sequel', adaptation: 'Adaptation', delay: 'Delay', cancellation: 'Cancellation', metadata_change: 'Metadata change' } as Record<string, string>)[kind] || kind; }
export function localToday() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
export function displayTimezone() { return new Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; }
export function releaseLabel(event: EventOut) {
  if (event.precision === 'unknown') return event.date_label || 'Date to be announced';
  if (event.precision === 'instant' && event.scheduled_at) return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(event.scheduled_at));
  if (event.precision === 'year' && event.window_start) return event.window_start.slice(0,4);
  if (event.precision === 'season') return event.date_label || `${event.window_start} – ${event.window_end}`;
  if (event.window_start) return new Intl.DateTimeFormat(undefined, event.precision === 'month' ? { month: 'long', year: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(event.window_start + 'T12:00:00'));
  return 'Date to be announced';
}
export function timestampLabel(value: string | null) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'Not provided by source'; }
