<script setup lang="ts">defineProps<{ eyebrow?: string; title: string; subtitle?: string }>();</script>
<template><header class="page-heading"><div><div class="eyebrow">{{ eyebrow || 'YOUR STORIES, IN ORDER' }}</div><h1>{{ title }}</h1><p v-if="subtitle">{{ subtitle }}</p></div><div class="heading-actions"><slot /></div></header></template>
