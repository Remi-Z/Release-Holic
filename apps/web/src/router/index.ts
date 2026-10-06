import { defineRouter } from '#q-app/wrappers';
import { createRouter, createWebHashHistory } from 'vue-router';
import { restoreSession, token, clearSession } from '../api/client';

export default defineRouter(() => {
  const router = createRouter({
    history: createWebHashHistory(),
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes: [
      { path: '/login', component: () => import('../pages/LoginPage.vue') },
      { path: '/', component: () => import('../layouts/AppLayout.vue'), children: [
        { path: '', component: () => import('../pages/TimelinePage.vue') },
        { path: 'library', component: () => import('../pages/LibraryPage.vue') },
        { path: 'works/:id', component: () => import('../pages/WorkPage.vue') },
        { path: 'review', component: () => import('../pages/ReviewPage.vue') },
        { path: 'sources', component: () => import('../pages/SourcesPage.vue') },
        { path: 'settings', component: () => import('../pages/SettingsPage.vue') },
      ] },
      { path: '/:pathMatch(.*)*', redirect: '/' },
    ],
  });
  router.beforeEach(async (to) => {
    if (to.path === '/login') return true;
    if (!token.value || !(await restoreSession())) return '/login';
    return true;
  });
  window.addEventListener('session-expired', () => { clearSession(); void router.replace('/login'); });
  return router;
});
