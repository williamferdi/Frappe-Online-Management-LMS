/**
 * The one place that talks to Frappe.
 *
 * Same-origin, so the session is Frappe's own `sid` cookie -- there is no token
 * to store or refresh. Writes carry the CSRF token that `_portal.py` put on the
 * page at boot.
 */

export interface Boot {
	csrf_token: string
	user: string
	full_name: string
	user_image: string | null
	roles: string[]
	student: string | null
	enrollment: string | null
	site_name: string
	app_version: string
}

const GUEST: Boot = {
	csrf_token: '',
	user: 'Guest',
	full_name: 'Guest',
	user_image: null,
	roles: ['Guest'],
	student: null,
	enrollment: null,
	site_name: '',
	app_version: '',
}

/**
 * Boot data injected by Jinja as globals (see plugins/jinja-boot.ts).
 *
 * Frappe writes the string "None" for a null, which is not a value any caller
 * wants to see -- the CSRF guard in particular treats "None" as a real token
 * and then fails the request.
 */
export function readBoot(): Boot {
	const w = window as unknown as Record<string, unknown>
	const str = (key: string, fallback = ''): string => {
		const value = w[key]
		return typeof value === 'string' && value !== 'None' ? value : fallback
	}

	if (!w.user && !w.csrf_token) return GUEST

	return {
		csrf_token: str('csrf_token'),
		user: str('user', 'Guest'),
		full_name: str('full_name', str('user', 'Guest')),
		user_image: str('user_image') || null,
		roles: Array.isArray(w.roles) ? (w.roles as string[]) : ['Guest'],
		student: str('student') || null,
		enrollment: str('enrollment') || null,
		site_name: str('site_name'),
		app_version: str('app_version'),
	}
}

export const boot: Boot = readBoot()

export class FrappeError extends Error {
	readonly status: number
	readonly excType: string
	readonly messages: string[]

	constructor(message: string, status: number, excType = '', messages: string[] = []) {
		super(message)
		this.name = 'FrappeError'
		this.status = status
		this.excType = excType
		this.messages = messages
	}

	/** A session that has expired, rather than a rule the user broke. */
	get isAuthError(): boolean {
		return this.status === 401 || this.excType === 'SessionExpired'
	}

	get isPermissionError(): boolean {
		return this.status === 403 || this.excType === 'PermissionError'
	}
}

/**
 * Frappe reports user-facing failures in `_server_messages`: a JSON string
 * holding an array of JSON strings, each an object with the actual message.
 * Two levels of encoding, and the useful text is at the bottom of both.
 */
function serverMessages(payload: Record<string, unknown>): string[] {
	const raw = payload._server_messages
	if (typeof raw !== 'string') return []

	try {
		const entries = JSON.parse(raw) as unknown
		if (!Array.isArray(entries)) return []

		return entries
			.map((entry) => {
				if (typeof entry !== 'string') return ''
				try {
					const parsed = JSON.parse(entry) as { message?: string }
					return parsed.message ?? ''
				} catch {
					return entry
				}
			})
			.map(stripHtml)
			.filter(Boolean)
	} catch {
		return []
	}
}

function stripHtml(value: string): string {
	const el = document.createElement('div')
	el.innerHTML = value
	return (el.textContent ?? '').trim()
}

interface CallOptions {
	method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
	args?: Record<string, unknown>
	signal?: AbortSignal
}

/**
 * Call a whitelisted method and return what it returned.
 *
 * Frappe wraps every RPC result in `{ message: ... }`; callers want the value,
 * not the envelope.
 */
export async function frappeCall<T>(path: string, options: CallOptions = {}): Promise<T> {
	const { method = 'GET', args = {}, signal } = options

	const headers: Record<string, string> = { Accept: 'application/json' }
	let url = `/api/method/${path}`
	let body: string | undefined

	if (method === 'GET') {
		const query = new URLSearchParams()
		for (const [key, value] of Object.entries(args)) {
			if (value === undefined || value === null) continue
			query.set(key, typeof value === 'string' ? value : JSON.stringify(value))
		}
		const qs = query.toString()
		if (qs) url += `?${qs}`
	} else {
		headers['Content-Type'] = 'application/json'
		body = JSON.stringify(args)
	}

	// Frappe skips the CSRF check for guests, and rejects the literal "None".
	if (method !== 'GET' && boot.csrf_token) {
		headers['X-Frappe-CSRF-Token'] = boot.csrf_token
	}

	const response = await fetch(url, {
		method,
		headers,
		body,
		signal,
		credentials: 'same-origin',
	})

	const text = await response.text()
	let payload: Record<string, unknown> = {}
	if (text) {
		try {
			payload = JSON.parse(text) as Record<string, unknown>
		} catch {
			// An HTML error page, which means something upstream of Frappe.
			if (!response.ok) {
				throw new FrappeError(`${response.status} ${response.statusText}`, response.status)
			}
		}
	}

	if (!response.ok) {
		const messages = serverMessages(payload)
		const excType = typeof payload.exc_type === 'string' ? payload.exc_type : ''
		const message =
			messages[0] ||
			(typeof payload.message === 'string' ? payload.message : '') ||
			`${response.status} ${response.statusText}`
		throw new FrappeError(message, response.status, excType, messages)
	}

	return payload.message as T
}

export const frappeGet = <T>(path: string, args?: Record<string, unknown>) =>
	frappeCall<T>(path, { method: 'GET', args })

export const frappePost = <T>(path: string, args?: Record<string, unknown>) =>
	frappeCall<T>(path, { method: 'POST', args })

/**
 * Upload a file and get back the address Frappe stored it at.
 *
 * Its own function rather than a `frappeCall` option: this sends FormData, so
 * the browser must set the Content-Type itself — including the multipart
 * boundary, which is why the JSON header the rest of the API sets would break
 * it.
 */
export async function frappeUpload(
	file: File,
	options: { private?: boolean } = {},
): Promise<{ file_url: string; file_name: string }> {
	const form = new FormData()
	form.append('file', file, file.name)
	form.append('is_private', options.private === false ? '0' : '1')

	const headers: Record<string, string> = { Accept: 'application/json' }
	if (boot.csrf_token) headers['X-Frappe-CSRF-Token'] = boot.csrf_token

	const response = await fetch('/api/method/upload_file', {
		method: 'POST',
		headers,
		body: form,
		credentials: 'same-origin',
	})

	const text = await response.text()
	let payload: Record<string, unknown> = {}
	try {
		payload = text ? (JSON.parse(text) as Record<string, unknown>) : {}
	} catch {
		throw new FrappeError(`${response.status} ${response.statusText}`, response.status)
	}

	if (!response.ok) {
		const messages = serverMessages(payload)
		throw new FrappeError(
			messages[0] || `${response.status} ${response.statusText}`,
			response.status,
			typeof payload.exc_type === 'string' ? payload.exc_type : '',
			messages,
		)
	}

	return payload.message as { file_url: string; file_name: string }
}

/** Where a session belongs. `/` is Frappe's own website home, not this app. */
export const STUDENT_HOME = '/portal'
export const STAFF_HOME = '/staff'

export async function login(usr: string, pwd: string): Promise<void> {
	await frappeCall('login', { method: 'POST', args: { usr, pwd } })

	// The roles just changed, and the `boot` in memory is still the
	// signed-out copy -- the server injects boot data into the page, so only
	// a full load refreshes it. Ask who we are now rather than assuming: this
	// used to send everyone to /portal, which dropped staff into the student
	// portal with no sign that a console existed.
	let destination = STUDENT_HOME
	try {
		const session = await frappeCall<{ is_staff?: boolean }>(
			'sibbcs.api.session.boot',
		)
		if (session?.is_staff) destination = STAFF_HOME
	} catch {
		// Signing in did work. Landing on the portal is a poor guess for
		// staff, but the account switcher in the header gets them across.
	}

	window.location.assign(destination)
}

export async function logout(): Promise<void> {
	await frappeCall('logout', { method: 'POST' })
	window.location.assign('/portal/login')
}
