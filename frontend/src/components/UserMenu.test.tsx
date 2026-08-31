import { describe, expect, it, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

async function open(path: string, globals: Record<string, unknown>) {
	vi.resetModules()
	for (const key of ['user', 'roles', 'full_name', 'csrf_token']) {
		delete (window as unknown as Record<string, unknown>)[key]
	}
	Object.assign(window, globals)

	const { UserMenu } = await import('./UserMenu')
	render(
		<MemoryRouter initialEntries={[path]}>
			<UserMenu />
		</MemoryRouter>,
	)
	await userEvent.click(screen.getByRole('button', { name: /account menu/i }))
}

beforeEach(() => vi.resetModules())

describe('the account menu', () => {
	it('offers staff a way into the console from the portal', async () => {
		// Signing in as Administrator landed on /portal with nothing pointing at
		// the console, which read as the console not existing.
		await open('/portal', {
			user: 'Administrator',
			full_name: 'Administrator',
			roles: ['System Manager', 'Student'],
		})
		expect(await screen.findByRole('menuitem', { name: /staff console/i })).toBeInTheDocument()
	})

	it('offers a way back to the portal from the console, for someone who is both', async () => {
		await open('/staff', {
			user: 'Administrator',
			full_name: 'Administrator',
			roles: ['System Manager', 'Student'],
		})
		expect(await screen.findByRole('menuitem', { name: /student portal/i })).toBeInTheDocument()
	})

	it('does not offer the console to a plain student', async () => {
		await open('/portal', { user: 's@x.com', full_name: 'A Student', roles: ['Student'] })
		expect(screen.queryByRole('menuitem', { name: /staff console/i })).not.toBeInTheDocument()
		expect(screen.queryByRole('menuitem', { name: /frappe desk/i })).not.toBeInTheDocument()
	})

	it('does not offer the portal to staff who are not enrolled', async () => {
		await open('/staff', { user: 'r@x.com', full_name: 'A Registrar', roles: ['Registrar'] })
		expect(screen.queryByRole('menuitem', { name: /student portal/i })).not.toBeInTheDocument()
	})
})
