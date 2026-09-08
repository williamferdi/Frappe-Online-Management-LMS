import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { BookOpen, LayoutDashboard } from 'lucide-react'

import { AppShell, type NavSection } from './AppShell'

const sections: NavSection[] = [
	{
		items: [
			{ to: '/portal', label: 'Dashboard', icon: LayoutDashboard, end: true },
			{ to: '/portal/courses', label: 'My Courses', icon: BookOpen },
		],
	},
]

function renderShell(initial = '/portal') {
	return render(
		<MemoryRouter initialEntries={[initial]}>
			<Routes>
				<Route
					path="/portal"
					element={
						<AppShell product="Student Portal" sections={sections} />
					}
				>
					<Route index element={<p>Dashboard</p>} />
					<Route path="courses" element={<p>Courses</p>} />
				</Route>
			</Routes>
		</MemoryRouter>,
	)
}

beforeEach(() => window.localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('the main menu', () => {
	it('can be hidden and shown by hand', async () => {
		renderShell()

		await userEvent.click(screen.getByRole('button', { name: 'Hide the menu' }))
		expect(screen.getByRole('button', { name: 'Show the menu' })).toBeInTheDocument()

		await userEvent.click(screen.getByRole('button', { name: 'Show the menu' }))
		expect(screen.getByRole('button', { name: 'Hide the menu' })).toBeInTheDocument()
	})

	it('remembers the choice for next time', async () => {
		renderShell()
		await userEvent.click(screen.getByRole('button', { name: 'Hide the menu' }))

		expect(window.localStorage.getItem('sibbcs.nav.collapsed')).toBe('1')
	})

	it('stays put when a course is opened', async () => {
		// This is the one that changed: opening My Courses used to hide the
		// menu, and choosing a menu item is not a request to put the menu away.
		renderShell()
		expect(screen.getByRole('button', { name: 'Hide the menu' })).toBeInTheDocument()

		await userEvent.click(screen.getByRole('link', { name: 'My Courses' }))

		expect(screen.getByRole('button', { name: 'Hide the menu' })).toBeInTheDocument()
	})

	it('stays closed across pages once the reader closes it', async () => {
		// Somebody who closed it meant it -- on this page and on the next.
		// This is how a reader who does want the width on a course keeps it.
		renderShell()
		await userEvent.click(screen.getByRole('button', { name: 'Hide the menu' }))

		await userEvent.click(screen.getByRole('link', { name: 'My Courses' }))
		await userEvent.click(screen.getByRole('link', { name: 'Dashboard' }))

		expect(screen.getByRole('button', { name: 'Show the menu' })).toBeInTheDocument()
	})

	it('survives storage that refuses to answer', () => {
		// A private window with site data blocked throws on read, and a menu
		// that cannot render is a worse bug than a menu that forgets.
		vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
			throw new Error('denied')
		})

		renderShell()

		expect(screen.getByRole('link', { name: 'My Courses' })).toBeInTheDocument()
	})
})
