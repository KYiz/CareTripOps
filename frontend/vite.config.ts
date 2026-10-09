import { defineConfig } from 'vite';

export default defineConfig({
  server: { proxy: { '/api': { target: 'http://localhost:8000', ws: true }, '/readyz': 'http://localhost:8000' } },
});
