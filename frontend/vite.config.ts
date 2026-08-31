// defineConfig comes from vitest/config so the `test` block below typechecks;
// it re-exports Vite's own and adds the test options.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

import { jinjaBoot } from './plugins/jinja-boot.ts'

// Where the bench lives, so `yarn dev` can proxy to the running site.
const FRAPPE = process.env.FRAPPE_URL ?? 'http://127.0.0.1:8000'
const SITE = process.env.FRAPPE_SITE ?? 'test.local'

// Everything Frappe serves itself. Anything else falls through to the SPA, so
// a deep link like /portal/grades still boots the app in development.
const FRAPPE_PATHS = ['/api', '/assets', '/files', '/private', '/app', '/login', '/lms']

export default defineConfig({
	plugins: [react(), tailwindcss(), jinjaBoot()],

	resolve: {
		alias: { '@': path.resolve(import.meta.dirname, './src') },
	},

	build: {
		// Served by Frappe from sibbcs/public/portal at /assets/sibbcs/portal/.
		outDir: '../sibbcs/public/portal',
		emptyOutDir: true,
		// Off because the built bundle is committed, and a 2 MB map per build
		// bloats the repository. Turn it on temporarily to chase a live error.
		sourcemap: false,
	},

	server: {
		host: '0.0.0.0',
		allowedHosts: true,
		proxy: Object.fromEntries(
			FRAPPE_PATHS.map((route) => [
				route,
				{
					target: FRAPPE,
					changeOrigin: false,
					// The bench is multi-tenant by DNS, so a request arriving on
					// localhost has to say which site it means or Frappe answers
					// with the default one.
					headers: { Host: SITE, 'X-Frappe-Site-Name': SITE },
				},
			]),
		),
	},

	test: {
		environment: 'jsdom',
		globals: true,
		setupFiles: ['./src/test/setup.ts'],
		css: false,
	},
})
