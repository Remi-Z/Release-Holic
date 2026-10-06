<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { api, json, queryString, trackRun } from '../api/client';
import type { Candidate, FollowOut, RunOut, SearchOut } from '../api/contracts';
import { searchOpen, searchPrefill, report, success, mediaLabel } from '../composables/ui';

const router = useRouter();
const input = ref(''); const author = ref(''); const provider = ref('all');
const results = ref<SearchOut | null>(null); const loading = ref(false); const selecting = ref(''); const related = ref(false);
const providers = [{ label: 'All catalogues', value: 'all' }, { label: 'TMDB · Movies & shows', value: 'tmdb' }, { label: 'TVmaze · Shows', value: 'tvmaze' }, { label: 'Bangumi · Anime', value: 'bangumi' }, { label: 'Kakuyomu · Web novels', value: 'kakuyomu' }, { label: 'KADOKAWA · Books', value: 'kadokawa' }, { label: 'Gagaga · Books', value: 'gagaga' }, { label: 'NDL · Title / author / ISBN', value: 'ndl' }];
watch(searchOpen, open => { if (open) { input.value = searchPrefill.value; results.value = null; } });
async function search() {
  if (!input.value.trim() && !author.value.trim()) return;
  loading.value = true; results.value = null;
  const value = input.value.trim();
  const explicit = /^https:\/\/|^(tmdb|tvmaze|bangumi|kakuyomu|kadokawa|gagaga|ndl|isbn):|^[0-9Xx-]{10,20}$/.test(value);
  try { results.value = await api<SearchOut>('/search?' + queryString(explicit ? { value } : { query: value, author: author.value, provider: provider.value })); }
  catch (error) { report(error); } finally { loading.value = false; }
}
async function choose(candidate: Candidate) {
  selecting.value = `${candidate.provider}:${candidate.external_id}`;
  try {
    let workId = candidate.existing_work_id;
    if (workId) await api<FollowOut>('/library', json({ work_id: workId, include_related: related.value }));
    else {
      const run = await api<RunOut>('/catalogue/import', json({ provider: candidate.provider, namespace: candidate.namespace, external_id: candidate.external_id, include_related: related.value }));
      if (run.status === 'failed') throw new Error(run.message);
      trackRun(run); workId = run.work_id;
    }
    searchOpen.value = false; success(candidate.existing_work_id ? 'Added to your library' : 'Added to your library. Metadata collection is queued.');
    window.dispatchEvent(new Event('catalogue-updated'));
    if (workId) await router.push(`/works/${workId}`);
  } catch (error) { report(error); } finally { selecting.value = ''; }
}
</script>
<template><q-dialog v-model="searchOpen"><q-card class="search-dialog"><div class="panel-heading"><div><div class="eyebrow">FIND YOUR NEXT CHAPTER</div><h2>Add a story</h2></div><q-btn flat round icon="close" aria-label="Close search" v-close-popup /></div><q-form class="search-form" @submit="search"><q-input v-model="input" outlined autofocus label="Title, work URL, ISBN, or provider ID" placeholder="A title, kakuyomu.jp/works/…, or tmdb:movie:123" :maxlength="1000"><template #prepend><q-icon name="search" /></template></q-input><div class="form-row"><q-select v-model="provider" :options="providers" emit-value map-options outlined label="Catalogue" /><q-input v-model="author" outlined label="Author (optional)" :maxlength="500" /></div><q-btn type="submit" color="primary" unelevated label="Search catalogues" no-caps :loading="loading" :disable="!!selecting" /></q-form><div class="search-results"><q-banner v-if="results?.errors.length" class="soft-banner">Some sources couldn’t be searched. You can still select a result or try its direct URL.<q-expansion-item dense label="Source details"><p v-for="error in results.errors" :key="error">{{ error }}</p></q-expansion-item></q-banner><div v-if="results && !results.candidates.length" class="empty-state"><q-icon name="search_off" /><h3>No matching stories</h3><p>Try another catalogue, the original Japanese title, or a direct URL.</p></div><p v-if="!results && !loading" class="muted search-hint">A title can refer to several adaptations or editions. Choose the record you want to follow.</p><q-toggle v-if="results?.candidates.length" v-model="related" label="Also follow known sequels, adaptations, and spin-offs" color="primary" /><button v-for="candidate in results?.candidates" :key="`${candidate.provider}:${candidate.namespace}:${candidate.external_id}`" type="button" class="search-result" :disabled="!!selecting" @click="choose(candidate)"><span class="result-glyph"><q-icon name="auto_stories" /></span><span><strong>{{ candidate.title }}</strong><small>{{ mediaLabel(candidate.kind) }} · {{ candidate.provider }} {{ candidate.year ? `· ${candidate.year}` : '' }}</small><small v-if="candidate.creators?.length">{{ candidate.creators.join(', ') }}</small><small class="candidate-identity">{{ candidate.namespace }}:{{ candidate.external_id }}</small></span><q-spinner v-if="selecting === `${candidate.provider}:${candidate.external_id}`" /><q-icon v-else :name="candidate.existing_work_id ? 'add_task' : 'add'" /></button></div></q-card></q-dialog></template>
