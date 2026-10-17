import path from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { loadProfile, publicProfile, interpolate, escapeHtml, repoRoot } from './profile-config.mjs';

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, repoRoot, ''), ...process.env };
  const profile = loadProfile(env);
  return {
    envDir: repoRoot,
    plugins: [react(), {
      name: 'portfolio-profile',
      resolveId(id) { if (id === 'virtual:portfolio-profile') return '\0portfolio-profile'; },
      load(id) { if (id === '\0portfolio-profile') return `export default ${JSON.stringify(publicProfile(profile, env))}`; },
      transformIndexHtml(html) {
        const name = profile.resume.personalInfo.name;
        return html.replaceAll('__SITE_TITLE__', escapeHtml(interpolate(profile.site.title, name)))
          .replaceAll('__SITE_DESCRIPTION__', escapeHtml(interpolate(profile.site.description, name)))
          .replaceAll('__SITE_URL__', escapeHtml(profile.site.url || ''));
      },
    }],
    server: { host: '127.0.0.1', port: 3001, proxy: { '/api': {
      target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true,
      rewrite: value => value.replace(/^\/api/, ''),
    } } },
    resolve: { alias: { '@': path.resolve(repoRoot, 'services/frontend/src') } },
  };
});
