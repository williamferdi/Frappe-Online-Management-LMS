// A page that renders the real module builder against a course held in
// memory, for looking at in a browser. Never deployed.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { realpathSync } from 'node:fs'
import path from 'node:path'

// The long form of the path, or Vite's allow-list and the requested file spell
// the same folder two ways (ADMINI~1) and it refuses its own page.
const here = realpathSync.native(import.meta.dirname)
const frontend = path.resolve(here, '..')

export default defineConfig({
	root: here,
	plugins: [react(), tailwindcss()],
	resolve: {
		alias: [
			// Only the bare module: the stub imports the real one by path.
			{ find: /^@\/lib\/frappe$/, replacement: path.resolve(here, 'frappe-stub.ts') },
			{ find: '@', replacement: path.resolve(frontend, 'src') },
		],
	},
	server: { port: 5198, strictPort: true, fs: { allow: [frontend] } },
})
