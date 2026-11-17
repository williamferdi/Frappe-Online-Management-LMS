// A page that renders the real RichTextEditor, for looking at in a browser.
// jsdom implements no editing commands, so this is where the browser's half of
// the toolbar gets checked. Never deployed.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { realpathSync } from 'node:fs'
import path from 'node:path'

// The long form of the path. Launched through a Windows 8.3 short name
// (ADMINI~1), Vite's allow-list and the requested file spell the same folder
// two ways, and it refuses its own page.
const here = realpathSync.native(import.meta.dirname)
const frontend = path.resolve(here, '..')

export default defineConfig({
	root: here,
	plugins: [react(), tailwindcss()],
	resolve: { alias: { '@': path.resolve(frontend, 'src') } },
	server: { port: 5199, strictPort: true, fs: { allow: [frontend] } },
})
