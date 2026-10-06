import { defineConfig } from '#q-app/wrappers';

export default defineConfig(() => ({
  css: ['app.scss'],
  extras: ['material-icons'],
  build: {
    target: { browser: ['es2022', 'firefox115', 'chrome115', 'safari16.4'], node: 'node22' },
    vueRouterMode: 'hash',
    env: { API_BASE_URL: process.env.API_BASE_URL || '/api' },
    typescript: { strict: true, vueShim: true },
  },
  devServer: {
    port: 9000,
    open: false,
    proxy: Object.fromEntries(['/api', '/admin', '/static'].map(route => [route, { target: process.env.API_PROXY || 'http://127.0.0.1:8000', changeOrigin: true }])),
  },
  framework: { config: { brand: { primary: '#6854cf', secondary: '#283c42', accent: '#f0a96b', positive: '#398b6c', negative: '#c95561' } }, plugins: ['Notify', 'Dialog'] },
  animations: ['fadeIn', 'fadeOut'],
  pwa: { workboxMode: 'GenerateSW', manifestFilename: 'manifest.json', injectPwaMetaTags: true, extendGenerateSWOptions(config) { config.navigateFallbackDenylist = [/^\/api\//]; } },
  capacitor: { hideSplashscreen: true },
  electron: {
    bundler: 'builder',
    builder: { appId: 'com.releaseholic.app', productName: 'Release-Holic', directories: { output: 'dist/electron' } },
  },
}));
