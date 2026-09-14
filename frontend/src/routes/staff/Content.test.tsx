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
const upload = vi.fn(async (file: File) => ({
	file_url: `/private/files/${file.name}`,
	file_name: file.name,
}))

const READING = {
	name: 'CFL-00001',
	title: 'Reading list',
	file: '/private/files/reading.pdf',
	is_folder: 0,
	description: 'Chapters 1-3',
}

/** Answers each read by what it asks for: the outline, one page, one lesson. */
async function renderContent({
	data = outline(),
	onePage = async () => page(),
	oneLesson = async () => ({}),
}: {
	data?: ContentOutline
	onePage?: (args?: Record<string, unknown>) => Promise<unknown>
	oneLesson?: (args?: Record<string, unknown>) => Promise<unknown>
} = {}) {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return {
			...actual,
			frappeGet: vi.fn(async (path: string, args?: Record<string, unknown>) =>
				path.endsWith('.page')
					? onePage(args)
					: path.endsWith('.lesson')
						? oneLesson(args)
						: data,
			),
			frappePost: post,
			frappeUpload: upload,
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
	upload.mockClear()
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

	it('asks for the page through this course, so the server can refuse any other', async () => {
		let asked: Record<string, unknown> | undefined
		await renderContent({
			onePage: async (args) => {
				asked = args
				return page()
			},
		})

		await userEvent.click(await screen.findByRole('button', { name: 'Edit Syllabus' }))
		await screen.findByLabelText('Title')

		expect(asked).toEqual({ name: 'CP-0001', course_offering: OFFERING })
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
	it('asks for the lesson through this course, so the server can refuse any other', async () => {
		let asked: Record<string, unknown> | undefined
		await renderContent({
			data: outline({
				pages: [],
				chapters: [
					{ name: 'CH-1', title: 'Week One', lessons: [{ name: 'LES-1', title: 'Creation' }] },
				],
			}),
			oneLesson: async (args) => {
				asked = args
				return { name: 'LES-1', title: 'Creation', chapter: 'CH-1', blocks: [] }
			},
		})

		await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
		await screen.findByLabelText('Lesson title')

		expect(asked).toEqual({ name: 'LES-1', course_offering: OFFERING })
	})

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

describe('a course file', () => {
	it('can be previewed in a new tab', async () => {
		await renderContent({ data: outline({ files: [READING] }) })

		const link = await screen.findByRole('link', { name: 'Preview Reading list' })

		expect(link).toHaveAttribute('href', '/private/files/reading.pdf')
		expect(link).toHaveAttribute('target', '_blank')
	})

	it('offers a download where the browser cannot show the file', async () => {
		await renderContent({
			data: outline({ files: [{ ...READING, file: '/private/files/notes.docx' }] }),
		})

		expect(await screen.findByRole('link', { name: 'Download Reading list' })).toHaveAttribute(
			'href',
			'/private/files/notes.docx',
		)
	})

	it('opens for editing with its title and a preview of what is attached', async () => {
		await renderContent({ data: outline({ files: [READING] }) })

		await userEvent.click(await screen.findByRole('button', { name: 'Edit Reading list' }))

		expect(screen.getByLabelText('Title')).toHaveValue('Reading list')
		expect(screen.getByTitle('Preview of Reading list')).toHaveAttribute(
			'src',
			'/private/files/reading.pdf',
		)
	})

	it('saves a new title without touching the attachment', async () => {
		await renderContent({ data: outline({ files: [READING] }) })
		await userEvent.click(await screen.findByRole('button', { name: 'Edit Reading list' }))

		const title = screen.getByLabelText('Title')
		await userEvent.clear(title)
		await userEvent.type(title, 'Week one reading')
		await userEvent.click(screen.getByRole('button', { name: 'Save file' }))

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith('sibbcs.api.content.save_file', {
				course_offering: OFFERING,
				name: 'CFL-00001',
				title: 'Week one reading',
				description: 'Chapters 1-3',
			}),
		)
	})

	it('replaces the attachment, showing the new file before it is saved', async () => {
		await renderContent({ data: outline({ files: [READING] }) })
		await userEvent.click(await screen.findByRole('button', { name: 'Edit Reading list' }))

		await userEvent.upload(
			screen.getByLabelText('Replace file'),
			new File(['%PDF'], 'week2.pdf', { type: 'application/pdf' }),
		)

		await waitFor(() =>
			expect(screen.getByTitle('Preview of Reading list')).toHaveAttribute(
				'src',
				'/private/files/week2.pdf',
			),
		)
		expect(post).not.toHaveBeenCalled()

		await userEvent.click(screen.getByRole('button', { name: 'Save file' }))

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith('sibbcs.api.content.save_file', {
				course_offering: OFFERING,
				name: 'CFL-00001',
				title: 'Reading list',
				description: 'Chapters 1-3',
				file: '/private/files/week2.pdf',
			}),
		)
	})

	it('leaves the file as it was when the replacement is cancelled', async () => {
		await renderContent({ data: outline({ files: [READING] }) })
		await userEvent.click(await screen.findByRole('button', { name: 'Edit Reading list' }))

		await userEvent.upload(
			screen.getByLabelText('Replace file'),
			new File(['%PDF'], 'week2.pdf', { type: 'application/pdf' }),
		)
		await screen.findByText(/week2\.pdf takes the old file's place/)
		await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

		expect(post).not.toHaveBeenCalled()
		expect(await screen.findByRole('link', { name: 'Preview Reading list' })).toHaveAttribute(
			'href',
			'/private/files/reading.pdf',
		)
	})
})

describe('describing a file for students', () => {
	it('saves the description written for it', async () => {
		await renderContent({ data: outline({ files: [READING] }) })
		await userEvent.click(await screen.findByRole('button', { name: 'Edit Reading list' }))

		const description = screen.getByLabelText('Description')
		expect(description).toHaveValue('Chapters 1-3')
		await userEvent.clear(description)
		await userEvent.type(description, 'Read before Tuesday')
		await userEvent.click(screen.getByRole('button', { name: 'Save file' }))

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith(
				'sibbcs.api.content.save_file',
				expect.objectContaining({ name: 'CFL-00001', description: 'Read before Tuesday' }),
			),
		)
	})

	it('takes a description as the file is added', async () => {
		await renderContent()
		await userEvent.click(await screen.findByRole('button', { name: /Add file/ }))

		await userEvent.upload(
			screen.getByLabelText('File'),
			new File(['%PDF'], 'week1.pdf', { type: 'application/pdf' }),
		)
		await screen.findByText('Uploaded week1.pdf')
		await userEvent.type(screen.getByLabelText('Description'), 'For the first seminar')
		await userEvent.click(screen.getByRole('button', { name: 'Add' }))

		await waitFor(() =>
			expect(post).toHaveBeenCalledWith('sibbcs.api.content.save_file', {
				course_offering: OFFERING,
				title: 'week1.pdf',
				file: '/private/files/week1.pdf',
				description: 'For the first seminar',
			}),
		)
	})
})
