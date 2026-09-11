import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { ContentOutline } from '@/types'

const OFFERING = 'THST601-TERM-A'

const SYLLABUS = {
	name: 'CP-0001',
	title: 'Syllabus',
	published: 1,
	modified: '2026-09-01 10:00:00',
}

function outline(over: Partial<ContentOutline> = {}): ContentOutline {
	return {
		course: 'THST601',
		lms_course: 'LMS-THST601',
		chapters: [],
		pages: [SYLLABUS],
		files: [],
		block_types: ['paragraph'],
		...over,
	}
}

function page(over: Record<string, unknown> = {}) {
	return {
		name: 'CP-0001',
		course: 'THST601',
		title: 'Syllabus',
		body: '<p>Week one: Genesis.</p>',
		published: 1,
		...over,
	}
}

const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({}))

/** Answers each read by what it asks for: the outline, one page, one lesson. */
async function renderContent({
	data = outline(),
	onePage = async () => page(),
	oneLesson = async () => ({}),
}: {
	data?: ContentOutline
	onePage?: () => Promise<unknown>
	oneLesson?: () => Promise<unknown>
} = {}) {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return {
			...actual,
			frappeGet: vi.fn(async (path: string) =>
				path.endsWith('.page') ? onePage() : path.endsWith('.lesson') ? oneLesson() : data,
			),
			frappePost: post,
		}
	})

	const { Content } = await import('./Content')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter>
				<Content offering={OFFERING} />
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
}

beforeEach(() => {
	vi.resetModules()
	post.mockClear()
})
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('editing a page', () => {
	it('opens an existing page with what it already says', async () => {
		await renderContent()

		await userEvent.click(await screen.findByRole('button', { name: 'Edit Syllabus' }))

		expect(await screen.findByLabelText('Title')).toHaveValue('Syllabus')
		expect(screen.getByRole('textbox', { name: 'Body' })).toContainHTML(
			'<p>Week one: Genesis.</p>',
		)
		expect(screen.getByRole('toolbar', { name: 'Formatting' })).toBeInTheDocument()
	})

	it('saves what was written with the formatting toolbar', async () => {
		await renderContent()
		await userEvent.click(await screen.findByRole('button', { name: 'Edit Syllabus' }))

		const body = await screen.findByRole('textbox', { name: 'Body' })
		body.innerHTML = '<p>Week one: <strong>Genesis</strong>.</p>'
		fireEvent.input(body)
		await userEvent.click(screen.getByRole('button', { name: 'Save page' }))

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith(
				'sibbcs.api.content.save_page',
				expect.objectContaining({
					name: 'CP-0001',
					body: '<p>Week one: <strong>Genesis</strong>.</p>',
				}),
			),
		)
	})

	it('saves the edit to the same page rather than making a new one', async () => {
		await renderContent()
		await userEvent.click(await screen.findByRole('button', { name: 'Edit Syllabus' }))

		const title = await screen.findByLabelText('Title')
		await userEvent.clear(title)
		await userEvent.type(title, 'Course syllabus')
		await userEvent.click(screen.getByRole('button', { name: 'Save page' }))

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith(
				'sibbcs.api.content.save_page',
				expect.objectContaining({
					course_offering: OFFERING,
					name: 'CP-0001',
					title: 'Course syllabus',
					body: '<p>Week one: Genesis.</p>',
				}),
			),
		)
	})

	it('keeps a draft a draft', async () => {
		// Saving used to send `published: 1` whatever the page was. Harmless
		// while pages could only be created; with Edit, it would publish a
		// draft the moment somebody fixed a typo in it.
		await renderContent({
			data: outline({ pages: [{ ...SYLLABUS, published: 0 }] }),
			onePage: async () => page({ published: 0 }),
		})
		await userEvent.click(await screen.findByRole('button', { name: 'Edit Syllabus' }))

		expect(
			await screen.findByRole('checkbox', { name: 'Students can see this page' }),
		).not.toBeChecked()
		await userEvent.click(screen.getByRole('button', { name: 'Save page' }))

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith(
				'sibbcs.api.content.save_page',
				expect.objectContaining({ name: 'CP-0001', published: 0 }),
			),
		)
	})

	it('publishes a draft when asked to', async () => {
		await renderContent({
			data: outline({ pages: [{ ...SYLLABUS, published: 0 }] }),
			onePage: async () => page({ published: 0 }),
		})
		await userEvent.click(await screen.findByRole('button', { name: 'Edit Syllabus' }))

		await userEvent.click(
			await screen.findByRole('checkbox', { name: 'Students can see this page' }),
		)
		await userEvent.click(screen.getByRole('button', { name: 'Save page' }))

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith(
				'sibbcs.api.content.save_page',
				expect.objectContaining({ name: 'CP-0001', published: 1 }),
			),
		)
	})

	it('still makes a new page, published, from New page', async () => {
		await renderContent()

		await userEvent.click(await screen.findByRole('button', { name: /New page/ }))
		await userEvent.type(screen.getByLabelText('Title'), 'Reading list')
		await userEvent.click(screen.getByRole('button', { name: 'Save page' }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]!
		expect(path).toBe('sibbcs.api.content.save_page')
		expect(args).toMatchObject({ title: 'Reading list', published: 1 })
		expect(args?.name).toBeUndefined()
	})

	it('does not open an empty editor over a page it could not load', async () => {
		// The editor takes its text once. Opened empty, its first Save would
		// write that emptiness over the page.
		await renderContent({
			onePage: async () => {
				throw new Error('gone')
			},
		})

		await userEvent.click(await screen.findByRole('button', { name: 'Edit Syllabus' }))

		expect(await screen.findByText('This page could not be opened')).toBeInTheDocument()
		expect(screen.queryByRole('button', { name: 'Save page' })).toBeNull()
	})
})

describe('editing a lesson', () => {
	it('does not open an empty editor over a lesson it could not load', async () => {
		await renderContent({
			data: outline({
				pages: [],
				chapters: [
					{ name: 'CH-1', title: 'Week One', lessons: [{ name: 'LES-1', title: 'Creation' }] },
				],
			}),
			oneLesson: async () => {
				throw new Error('gone')
			},
		})

		await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))

		expect(await screen.findByText('This lesson could not be opened')).toBeInTheDocument()
		expect(screen.queryByRole('button', { name: 'Save lesson' })).toBeNull()
	})
})
