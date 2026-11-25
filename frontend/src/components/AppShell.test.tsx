import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { BookOpen, LayoutDashboard } from 'lucide-react'

import { AppShell, type NavSection } from './AppShell'

vi.mock('@/lib/frappe', async (original) => {
	const actual = await original<typeof import('@/lib/frappe')>()
	return {
		...actual,
		// A getter, because `boot` is a module constant read once at load and
		// each test needs its own answer. Spread over the real one so the rest
		// of it -- the roles UserMenu reads, for instance -- is still there.
		get boot() {
			return { ...actual.boot, ...bootStub }
		},
	}
})

/** Replaced per test; see the getter above. */
let bootStub: { lms_url: string } = { lms_url: '' }

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

beforeEach(() => {
	window.localStorage.clear()
	bootStub = { lms_url: '' }
})
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

describe('the way across to the helpdesk', () => {
	it('is drawn only for a shell that is given an address', () => {
		// The staff console is not given one.
		renderShell()

		expect(screen.queryByRole('link', { name: 'Helpdesk' })).not.toBeInTheDocument()
	})
})

describe('the way across to the learning site', () => {
	it('sits in the header, on every page', () => {
		// Not only on a course row in My Courses, which is where the single
		// door used to be -- a student on Grades had to go back to find it.
		bootStub = { lms_url: 'https://lms.example.invalid' }

		renderShell()

		expect(screen.getByRole('link', { name: 'LMS' })).toHaveAttribute(
			'href',
			'https://lms.example.invalid',
		)
	})

	it('opens in its own tab', () => {
		// It is a different application. Replacing the portal with it would
		// take the back button with it.
		bootStub = { lms_url: 'https://lms.example.invalid' }

		renderShell()

		expect(screen.getByRole('link', { name: 'LMS' })).toHaveAttribute('target', '_blank')
	})

	it('is not drawn at all where no learning site is configured', () => {
		// A link to nothing is worse than no link.
		renderShell()

		expect(screen.queryByRole('link', { name: 'LMS' })).not.toBeInTheDocument()
	})
})
