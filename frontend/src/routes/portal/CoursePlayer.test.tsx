import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { OutlineItem, PlayerCourse, PlayerItem } from '@/types'

/**
 * The player had no front-end test at all. These are the two the modules list
 * used to carry, which belong here now that a row leads to the player rather
 * than opening in place -- plus enough around them to prove the page renders.
 */

const REGISTRATION = 'REG-1'
const ITEM = 'CMI-00001'

function item(overrides: Partial<OutlineItem> = {}): OutlineItem {
	return {
		name: ITEM,
		module: 'CM-00001',
		item_type: 'Lesson',
		title: 'What Scripture is',
		position: 0,
		indent: 0,
		published: 1,
		lesson: 'lesson-1',
		assignment: null,
		page: null,
		file: null,
		url: null,
		completion_requirement: 'View it',
		min_score: null,
		progress: null,
		complete: false,
		locked: false,
		lock_reason: null,
		...overrides,
	}
}

function course(row: OutlineItem): PlayerCourse {
	return {
		registration: {
			name: REGISTRATION,
			course_title: 'Systematic Theology I',
			course_offering: 'THST601-TERM-A',
		},
		modules: [
			{
				name: 'CM-00001',
				title: 'Week One',
				position: 0,
				published: 1,
				unlock_at: null,
				require_sequential_progress: 0,
				prerequisites: [],
				state: { open: true, reason: null },
				complete: false,
				items: [row],
			},
		],
		progress: { done: 0, total: 1, percent: 0 },
		sequence: [ITEM],
	}
}

function reading(row: OutlineItem): PlayerItem {
	return {
		item: row,
		module: 'CM-00001',
		previous: null,
		next: null,
		position: { index: 1, total: 1 },
		content: {
			name: 'lesson-1',
			title: 'What Scripture is',
			blocks: [{ type: 'paragraph', data: { text: 'All Scripture is' } }],
			removed: [],
			lms_url: '/lms/courses/intro',
		},
		resources: [],
		note: null,
	}
}

const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({}))

async function renderPlayer(row: OutlineItem, over: Partial<PlayerItem> = {}) {
	vi.resetModules()
	Object.assign(window, { user: 'student@x.com', roles: ['Student'], csrf_token: 't' })

	const get = vi.fn(async (path: string) =>
		path === 'sibbcs.api.player.item' ? { ...reading(row), ...over } : course(row),
	)

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: get, frappePost: post }
	})

	const { CoursePlayer } = await import('./CoursePlayer')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter
				initialEntries={[`/portal/courses/${REGISTRATION}/learn/${ITEM}`]}
			>
				<Routes>
					<Route
						path="/portal/courses/:name/learn/:item"
						element={<CoursePlayer />}
					/>
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
	await screen.findAllByText('What Scripture is')
}

beforeEach(() => {
	vi.resetModules()
	post.mockClear()
})
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('a file in the player', () => {
	const file = () => item({ item_type: 'File', lesson: null, file: 'CFL-00001' })
	const readingList = (description: string | null) => ({
		content: { title: 'Reading list', file: '/private/files/reading.pdf', description },
	})

	it('shows what the teacher wrote about it, with the file', async () => {
		await renderPlayer(file(), readingList('Read chapters 1-3 before Tuesday.'))

		expect(screen.getByText('Read chapters 1-3 before Tuesday.')).toBeInTheDocument()
		expect(screen.getByRole('link', { name: 'Reading list' })).toHaveAttribute(
			'href',
			'/private/files/reading.pdf',
		)
	})

	it('draws the description as text, not as markup', async () => {
		await renderPlayer(file(), readingList('Bring a pen.\n<b>Not bold</b>'))

		const said = screen.getByText(/Bring a pen\./)
		expect(said).toHaveTextContent('<b>Not bold</b>')
		expect(said.querySelector('b')).toBeNull()
	})

	it('shows each resource with what was written about it', async () => {
		await renderPlayer(item(), {
			resources: [
				{
					item: 'CMI-00002',
					title: 'Glossary',
					url: '/private/files/glossary.pdf',
					description: 'Terms for week one',
				},
			],
		})

		expect(screen.getByText('Terms for week one')).toBeInTheDocument()
		// The description sits beside the link, so the link is still named by
		// its title alone.
		expect(screen.getByRole('link', { name: 'Glossary' })).toHaveAttribute(
			'href',
			'/private/files/glossary.pdf',
		)
	})
})

describe('reading a lesson in the player', () => {
	it('shows the lesson a row led to', async () => {
		await renderPlayer(item())

		expect(screen.getByText('All Scripture is')).toBeInTheDocument()
	})

	it('offers the whole course as a list, not only where to resume', async () => {
		// The modules page had nothing linking to it for weeks and no test
		// noticed. That is this test's whole job: it does not care where the
		// way in lives, only that there is one.
		await renderPlayer(item())

		const link = screen.getByRole('link', { name: 'Modules' })
		expect(link.getAttribute('href')).toBe(`/portal/courses/${REGISTRATION}/modules`)
	})

	it('does not call two different things Modules', async () => {
		// One loads a page, one folds the list beside it. Told apart by eye
		// from their shape, and by ear only if they are named differently.
		await renderPlayer(item())

		expect(
			screen.getByRole('button', { name: /module list/i }),
		).toBeInTheDocument()
		expect(screen.queryByRole('button', { name: 'Modules' })).toBeNull()
	})

	it('offers Mark done only for the items that ask for it', async () => {
		await renderPlayer(item({ completion_requirement: 'Mark it done' }))

		await userEvent.click(screen.getByRole('button', { name: /Mark done/ }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.syllabus.mark_done')
		expect(args?.module_item).toBe(ITEM)
	})

	it('does not offer Mark done for work that is scored', async () => {
		// Letting a student declare marked work finished is letting them mark
		// their own work.
		await renderPlayer(
			item({ completion_requirement: 'Score at least', min_score: 50 }),
		)

		expect(screen.queryByRole('button', { name: /Mark done/ })).toBeNull()
	})

	it('says a finished lesson is finished', async () => {
		// The button used to just stop being there, which reads exactly like a
		// lesson that never asked to be marked in the first place.
		await renderPlayer(
			item({ completion_requirement: 'Mark it done', complete: true }),
		)

		expect(screen.queryByRole('button', { name: /Mark done/ })).toBeNull()
		expect(within(screen.getByRole('article')).getByText('Done')).toBeInTheDocument()
	})

	it('says which module the lesson is in', async () => {
		// "1 of 4" says how far along somebody is and nothing about where.
		await renderPlayer(item())

		expect(within(screen.getByRole('article')).getByText('Week One')).toBeInTheDocument()
	})
})
