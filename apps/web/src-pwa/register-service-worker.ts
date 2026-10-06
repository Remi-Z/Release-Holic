import { register } from 'register-service-worker';
import { Notify } from 'quasar';

register(process.env.SERVICE_WORKER_FILE || '/service-worker.js', {
  updated(registration) {
    Notify.create({ message: 'A new version is ready.', color: 'primary', timeout: 0, actions: [{ label: 'Reload', color: 'white', handler: () => { if (!registration.waiting) { window.location.reload(); return; } navigator.serviceWorker.addEventListener('controllerchange', () => window.location.reload(), { once: true }); registration.waiting.postMessage({ type: 'SKIP_WAITING' }); } }] });
  },
});
