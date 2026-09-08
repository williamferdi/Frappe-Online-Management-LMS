import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

const here = import.meta.dirname
const root = path.resolve(here, '..')

/**
 * A build of the staff course page with the network stubbed, so the screen can
 * be looked at without a session. Everything but the fetch is the real app.
 */
export default defineConfig({
	root: here,
	base: './',
	plugins: [react(), tailwindcss()],
	resolve: {
		alias: [
			// Exact match first, or the `@` rule below would swallow it.
			{
				find: /^@\/lib\/frappe$/,
				replacement: path.resolve(here, 'frappe-stub.ts'),
			},
			{ find: /^@\//, replacement: path.resolve(root, 'src') + '/' },
		],
	},
	build: {
		outDir: path.resolve(here, 'dist'),
		emptyOutDir: true,
	},
})
