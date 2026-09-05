import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { CourseOutline, OutlineItem } from '@/types'

const REGISTRATION = 'REG-1'

function item(overrides: Partial<OutlineItem> = {}): OutlineItem {
	return {
		name: 'CMI-00001',
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

function outline(overrides: Partial<CourseOutline['modules'][0]> = {}): CourseOutline {
	return {
		registration: {
			name: REGISTRATION,
			course_title: 'Systematic Theology I',
			course_offering: 'THST601-TERM-A',
			status: 'Active',
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
				items: [item()],
				...overrides,
			},
		],
	}
}

const get = vi.fn()
const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({}))

async function renderCourse(data: CourseOutline) {
	vi.resetModules()
	Object.assign(window, { user: 'student@x.com', roles: ['Student'], csrf_token: 't' })

	get.mockImplementation(async (path: string) => {
		if (path === 'sibbcs.api.syllabus.read_item') {
			return {
				item: item(),
				content: {
					name: 'lesson-1',
					title: 'What Scripture is',
					blocks: [{ type: 'paragraph', data: { text: 'All Scripture is' } }],
					removed: [],
					lms_url: '/lms/courses/intro',
				},
			}
		}
		return data
	})

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: get, frappePost: post }
	})

	const { MyCourse } = await import('./MyCourse')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter initialEntries={[`/portal/courses/${REGISTRATION}/modules`]}>
				<Routes>
					<Route path="/portal/courses/:name/modules" element={<MyCourse />} />
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
}

beforeEach(() => {
	vi.resetModules()
	get.mockClear()
	post.mockClear()
})
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('a student walking through a course', () => {
	it('lists the modules and what is in them', async () => {
		await renderCourse(outline())

		expect(screen.getByText('Week One')).toBeInTheDocument()
		expect(screen.getByRole('button', { name: 'What Scripture is' })).toBeEnabled()
	})

	it('reads a lesson without leaving the app', async () => {
		await renderCourse(outline())

		await userEvent.click(screen.getByRole('button', { name: 'What Scripture is' }))

		await waitFor(() =>
			expect(screen.getByText('All Scripture is')).toBeInTheDocument(),
		)
	})

	it('says why a locked module is locked, rather than just refusing', async () => {
		// "Why can't I open this?" is the question the registrar otherwise
		// answers by email.
		await renderCourse(
			outline({
				state: { open: false, reason: 'This opens on 12 Oct 2026, 09:00.' },
				items: [item({ locked: true, lock_reason: 'This opens on 12 Oct 2026, 09:00.' })],
			}),
		)

		expect(screen.getAllByText(/opens on 12 Oct 2026/).length).toBeGreaterThan(0)
		expect(screen.getByRole('button', { name: 'What Scripture is' })).toBeDisabled()
	})

	it('names the module that has to be finished first', async () => {
		await renderCourse(
			outline({
				state: { open: false, reason: 'Finish Week One first.' },
				items: [item({ locked: true, lock_reason: 'Finish Week One first.' })],
			}),
		)

		expect(screen.getAllByText('Finish Week One first.').length).toBeGreaterThan(0)
	})

	it('offers Mark done only for the items that ask for it', async () => {
		await renderCourse(
			outline({ items: [item({ completion_requirement: 'Mark it done' })] }),
		)

		await userEvent.click(screen.getByRole('button', { name: 'What Scripture is' }))
		await waitFor(() =>
			expect(screen.getByRole('button', { name: 'Mark done' })).toBeInTheDocument(),
		)

		await userEvent.click(screen.getByRole('button', { name: 'Mark done' }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.syllabus.mark_done')
	})

	it('does not offer Mark done for work that is scored', async () => {
		// Letting a student declare marked work finished is letting them mark
		// their own work.
		await renderCourse(
			outline({
				items: [item({ completion_requirement: 'Score at least', min_score: 50 })],
			}),
		)

		await userEvent.click(screen.getByRole('button', { name: 'What Scripture is' }))

		expect(screen.queryByRole('button', { name: 'Mark done' })).toBeNull()
	})

	it('says when there is nothing published yet', async () => {
		await renderCourse({ ...outline(), modules: [] })

		expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
	})
})
