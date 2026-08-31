import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * `boot` is read from window globals at module load, so each test that cares
 * about the session has to set those up and then import a fresh copy.
 */
async function loadWith(globals: Record<string, unknown>) {
	vi.resetModules()
	for (const key of ['user', 'csrf_token', 'roles', 'full_name', 'student']) {
		delete (window as unknown as Record<string, unknown>)[key]
	}
	Object.assign(window, globals)
	return import('./frappe')
}

/**
 * A fresh Response per call. Handing the same one back twice fails with
 * 'Body has already been read' -- a body is a stream, not a value.
 */
function responds(body: unknown, init: ResponseInit = {}) {
	return () =>
		Promise.resolve(
			new Response(typeof body === 'string' ? body : JSON.stringify(body), {
				status: 200,
				headers: { 'Content-Type': 'application/json' },
				...init,
			}),
		)
}

beforeEach(() => {
	vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
	vi.unstubAllGlobals()
	vi.restoreAllMocks()
})

describe('readBoot', () => {
	it('falls back to Guest when the page carried no boot data', async () => {
		const { readBoot } = await loadWith({})
		expect(readBoot().user).toBe('Guest')
	})

	it('treats the string "None" as absent', async () => {
		// Frappe writes "None" for an unset value. Passed through, it becomes a
		// CSRF token the server then rejects -- which is what broke the manual
		// acknowledgement form.
		const { readBoot } = await loadWith({
			user: 'v@example.com',
			csrf_token: 'None',
			user_image: 'None',
		})
		const session = readBoot()
		expect(session.csrf_token).toBe('')
		expect(session.user_image).toBeNull()
	})

	it('reads the fields the shell needs', async () => {
		const { readBoot } = await loadWith({
			user: 'v@example.com',
			full_name: 'Vignesh G',
			csrf_token: 'abc123',
			roles: ['Student', 'LMS Student'],
			student: 'SIB-2026-0002',
		})
		expect(readBoot()).toMatchObject({
			user: 'v@example.com',
			full_name: 'Vignesh G',
			csrf_token: 'abc123',
			roles: ['Student', 'LMS Student'],
			student: 'SIB-2026-0002',
		})
	})
})

describe('frappeCall', () => {
	it('unwraps the message envelope', async () => {
		const { frappeGet } = await loadWith({ user: 'a@b.c' })
		vi.mocked(fetch).mockImplementation(responds({ message: { registrations: [] } }))

		await expect(frappeGet('sibbcs.api.student.my_courses')).resolves.toEqual({
			registrations: [],
		})
	})

	it('sends the CSRF token on writes and not on reads', async () => {
		const { frappeGet, frappePost } = await loadWith({
			user: 'a@b.c',
			csrf_token: 'tok',
		})
		vi.mocked(fetch).mockImplementation(responds({ message: 1 }))

		await frappeGet('some.method')
		await frappePost('some.method', { x: 1 })

		const [readInit, writeInit] = vi.mocked(fetch).mock.calls.map((call) => call[1])
		expect((readInit?.headers as Record<string, string>)['X-Frappe-CSRF-Token']).toBeUndefined()
		expect((writeInit?.headers as Record<string, string>)['X-Frappe-CSRF-Token']).toBe('tok')
	})

	it('omits the CSRF header entirely when there is no token', async () => {
		// Guests have no token and Frappe does not want one; sending an empty
		// header fails the check rather than skipping it.
		const { frappePost } = await loadWith({ user: 'Guest' })
		vi.mocked(fetch).mockImplementation(responds({ message: 1 }))

		await frappePost('some.method')

		const init = vi.mocked(fetch).mock.calls[0]?.[1]
		expect((init?.headers as Record<string, string>)['X-Frappe-CSRF-Token']).toBeUndefined()
	})

	it('puts GET arguments in the query string, serialising non-strings', async () => {
		const { frappeGet } = await loadWith({ user: 'a@b.c' })
		vi.mocked(fetch).mockImplementation(responds({ message: 1 }))

		await frappeGet('some.method', { name: 'APP-1', limit: 20, skip: undefined })

		const url = vi.mocked(fetch).mock.calls[0]?.[0] as string
		expect(url).toContain('name=APP-1')
		expect(url).toContain('limit=20')
		expect(url).not.toContain('skip')
	})

	it('reads the real message out of _server_messages', async () => {
		const { frappeGet, FrappeError } = await loadWith({ user: 'a@b.c' })
		// Two levels of JSON encoding, and the text is at the bottom of both.
		vi.mocked(fetch).mockImplementation(
			responds(
				{
					exc_type: 'ValidationError',
					_server_messages: JSON.stringify([
						JSON.stringify({ message: '<b>Level 4 requires every Level 3 course.</b>' }),
					]),
				},
				{ status: 417 },
			),
		)

		await expect(frappeGet('some.method')).rejects.toMatchObject({
			message: 'Level 4 requires every Level 3 course.',
			excType: 'ValidationError',
		})
		await expect(frappeGet('some.method')).rejects.toBeInstanceOf(FrappeError)
	})

	it('classifies permission and auth failures', async () => {
		const { frappeGet } = await loadWith({ user: 'a@b.c' })

		vi.mocked(fetch).mockImplementation(
			responds({ exc_type: 'PermissionError' }, { status: 403 }),
		)
		await expect(frappeGet('m')).rejects.toMatchObject({ isPermissionError: true })

		vi.mocked(fetch).mockImplementation(responds({}, { status: 401 }))
		await expect(frappeGet('m')).rejects.toMatchObject({ isAuthError: true })
	})

	it('survives an HTML error page from in front of Frappe', async () => {
		const { frappeGet } = await loadWith({ user: 'a@b.c' })
		vi.mocked(fetch).mockImplementation(
			responds('<html>502 Bad Gateway</html>', {
				status: 502,
				headers: { 'Content-Type': 'text/html' },
			}),
		)

		await expect(frappeGet('m')).rejects.toMatchObject({ status: 502 })
	})
})

describe('where signing in lands you', () => {
	it('sends staff to the console, not the student portal', async () => {
		// The bug: login() assigned '/portal' unconditionally, so signing in
		// as Administrator opened the student portal and nothing on the page
		// suggested a staff console existed.
		const { login } = await loadWith({ user: 'Guest' })
		const assign = vi.fn()
		vi.stubGlobal('location', { assign })
		vi.mocked(fetch)
			.mockImplementationOnce(responds({ message: 'Logged In' }))
			.mockImplementationOnce(responds({ message: { is_staff: true } }))

		await login('Administrator', 'secret')
		expect(assign).toHaveBeenCalledWith('/staff')
	})

	it('sends a student to the portal', async () => {
		const { login } = await loadWith({ user: 'Guest' })
		const assign = vi.fn()
		vi.stubGlobal('location', { assign })
		vi.mocked(fetch)
			.mockImplementationOnce(responds({ message: 'Logged In' }))
			.mockImplementationOnce(responds({ message: { is_staff: false } }))

		await login('s@example.com', 'secret')
		expect(assign).toHaveBeenCalledWith('/portal')
	})

	it('still lands somewhere if the follow-up call fails', async () => {
		// The sign-in itself succeeded; stranding the user on the form
		// because a second request failed would be worse than a poor guess.
		const { login } = await loadWith({ user: 'Guest' })
		const assign = vi.fn()
		vi.stubGlobal('location', { assign })
		vi.mocked(fetch)
			.mockImplementationOnce(responds({ message: 'Logged In' }))
			.mockImplementationOnce(responds({}, { status: 500 }))

		await login('a@example.com', 'secret')
		expect(assign).toHaveBeenCalledWith('/portal')
	})

	it('does not send a bad password anywhere', async () => {
		const { login } = await loadWith({ user: 'Guest' })
		const assign = vi.fn()
		vi.stubGlobal('location', { assign })
		vi.mocked(fetch).mockImplementation(responds({}, { status: 401 }))

		await expect(login('a@example.com', 'wrong')).rejects.toBeTruthy()
		expect(assign).not.toHaveBeenCalled()
	})
})
