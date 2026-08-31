import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'

const setSession = (globals: Record<string, unknown>) => {
	for (const key of ['user', 'roles', 'csrf_token']) {
		delete (window as unknown as Record<string, unknown>)[key]
	}
	Object.assign(window, globals)
}

async function renderAt(path: string, globals: Record<string, unknown>) {
	vi.resetModules()
	setSession(globals)

	const { MemoryRouter, Route, Routes } = await import('react-router-dom')
	const { RequireAuth } = await import('./RequireAuth')

	render(
		<MemoryRouter initialEntries={[path]}>
			<Routes>
				<Route path="/portal/login" element={<div>sign in</div>} />
				<Route element={<RequireAuth />}>
					<Route path="/portal" element={<div>portal</div>} />
				</Route>
				<Route element={<RequireAuth staffOnly />}>
					<Route path="/staff" element={<div>console</div>} />
				</Route>
			</Routes>
		</MemoryRouter>,
	)
}

beforeEach(() => setSession({}))
afterEach(() => vi.restoreAllMocks())

describe('RequireAuth', () => {
	it('sends a signed-out visitor to sign in', async () => {
		await renderAt('/portal', { user: 'Guest', roles: ['Guest'] })
		expect(screen.getByText('sign in')).toBeInTheDocument()
	})

	it('keeps a student out of the console', async () => {
		await renderAt('/staff', { user: 's@x.com', roles: ['Student'] })
		expect(screen.queryByText('console')).not.toBeInTheDocument()
	})

	it('lets a registrar into the console', async () => {
		await renderAt('/staff', { user: 'r@x.com', roles: ['Registrar'] })
		expect(screen.getByText('console')).toBeInTheDocument()
	})

	it('lets a student into the portal', async () => {
		await renderAt('/portal', { user: 's@x.com', roles: ['Student'] })
		expect(screen.getByText('portal')).toBeInTheDocument()
	})
})
