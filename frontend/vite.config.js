import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  // Root = frontend/ (where package.json lives)
  root: '.',

  server: {
    port: 3000,
    open: '/login',

    // Proxy API calls to Django backend — no more CORS issues in dev
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },

  // Clean URL rewrites — /project_overview → project_dashboard.html etc.
  appType: 'mpa',
  plugins: [
    {
      name: 'clean-urls',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const rewrites = {
            '/':                 '/login.html',
            '/project_overview': '/project_dashboard.html',
            '/integrations':     '/integrations.html',
            '/login':            '/login.html',
            '/register':         '/register.html',
            '/forgot_password':  '/forgot_password.html',
            '/detail':           '/detail.html',
            '/home':             '/home.html',
            '/employee':         '/employee_personal.html',
          };
          if (rewrites[req.url]) {
            req.url = rewrites[req.url];
          }
          next();
        });
      },
    },
  ],

  // Multi-page build: list every HTML entry point
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'project_dashboard.html'),
        integrations: resolve(__dirname, 'integrations.html'),
        login: resolve(__dirname, 'login.html'),
        register: resolve(__dirname, 'register.html'),
        forgot_password: resolve(__dirname, 'forgot_password.html'),
        detail: resolve(__dirname, 'detail.html'),
        home: resolve(__dirname, 'home.html'),
        employee_personal: resolve(__dirname, 'employee_personal.html'),
      },
    },
  },
});
