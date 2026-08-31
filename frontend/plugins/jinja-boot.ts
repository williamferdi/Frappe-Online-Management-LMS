import type { Plugin } from 'vite'

/**
 * Hands the built index.html to Frappe as a Jinja template.
 *
 * Frappe renders `sibbcs/www/_portal.html` through Jinja before serving it, so
 * we can inject server state into the page instead of spending a round trip on
 * it at boot. `_portal.py` puts a dict on `context.boot`; this loop turns each
 * key into a global, which is exactly what Frappe LMS does in
 * `lms/www/_lms.html` -- and it is where `window.csrf_token` comes from.
 *
 * The tag must not be present in development: there is no Jinja there, and the
 * literal braces would be served to the browser as text.
 */
const BOOT_SCRIPT = [
	'<script>',
	'{% for key in boot %}window["{{ key }}"] = {{ boot[key] | tojson }};{% endfor %}',
	'</script>',
].join('\n\t\t')

export function jinjaBoot(): Plugin {
	return {
		name: 'sibbcs-jinja-boot',
		apply: 'build',
		transformIndexHtml: {
			order: 'post',
			handler(html) {
				return html.replace('</head>', `\t${BOOT_SCRIPT}\n\t</head>`)
			},
		},
	}
}
