import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { PortalLayout } from './PortalLayout'

/** The college specified this list and this order. Pin it. */
const EXPECTED = [
	'Dashboard',
	'My Courses',
	'To Do',
	'Calendar',
	'Inbox',
	'Grades',
	'Discussions',
	'Announcements',
	'Profile',
]

describe('student portal navigation', () => {
	it('offers the nine sections the college asked for, in order', () => {
		Object.assign(window, { user: 's@x.com', roles: ['Student'], full_name: 'A Student' })

		render(
			<MemoryRouter initialEntries={['/portal']}>
				<Routes>
					<Route path="/portal" element={<PortalLayout />}>
						<Route index element={<div />} />
					</Route>
				</Routes>
			</MemoryRouter>,
		)

		const labels = screen
			.getAllByRole('link')
			.map((link) => link.textContent?.trim())
			.filter((label) => EXPECTED.includes(label ?? ''))

		expect(labels).toEqual(EXPECTED)
	})
})
