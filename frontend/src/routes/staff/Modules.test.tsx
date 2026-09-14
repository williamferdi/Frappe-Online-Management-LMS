import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import type { OutlineItem, OutlineModule, StaffOutline } from '@/types'

const OFFERING = 'THST601-TERM-A'

function item(over: Partial<OutlineItem> = {}): OutlineItem {
	return {
		name: 'CMI-00001',
		module: 'CM-00001',
		item_type: 'Lesson',
		title: 'Lecture 1',
		position: 0,
		indent: 0,
		published: 1,
		lesson: 'LES-1',
		assignment: null,
		page: null,
		file: null,
		url: null,
		completion_requirement: 'Nothing',
		min_score: null,
		progress: null,
		complete: false,
		locked: false,
		lock_reason: null,
		...over,
	}
}

function unit(over: Partial<OutlineModule> = {}): OutlineModule {
	return {
		name: 'CM-00001',
		title: 'Week 1',
		position: 0,
		published: 1,
		unlock_at: null,
		require_sequential_progress: 0,
		prerequisites: [],
		state: { open: true, reason: null },
		complete: false,
		items: [],
		...over,
	}
}

function outline(modules: OutlineModule[]): StaffOutline {
	return {
		modules,
		choices: {
			// Non-empty, or the builder shows its "nowhere to write lessons"
			// panel instead of getting on with the modules.
			lessons: [{ name: 'LES-1', title: 'Lecture 1', chapter: 'CH-1' }],
			assignments: [],
			pages: [],
			files: [],
			item_types: ['Lesson', 'Assignment', 'Page', 'File', 'URL', 'Sub-header'],
			completion_rules: ['Nothing', 'View it', 'Mark it done'],
		},
	}
}

const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({}))

async function renderModules(data: StaffOutline) {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return {
			...actual,
			frappeGet: vi.fn(async (path: string) =>
				path.includes('content_space')
					? { course: 'THST601', lms_course: 'c', lessons: 1, authoring_url: null }
					: data,
			),
			frappePost: post,
		}
	})

	const { Modules } = await import('./Modules')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter>
				<Modules offering={OFFERING} />
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() => expect(document.querySelector('[data-slot="skeleton"]')).toBeNull())
	await screen.findByText('Week 1')
}

/** Opens a row or module's menu and picks one thing off it. */
async function choose(menu: string, entry: string) {
	await userEvent.click(screen.getByRole('button', { name: menu }))
	await userEvent.click(await screen.findByRole('menuitem', { name: entry }))
}

beforeEach(() => {
	vi.resetModules()
	post.mockClear()
})
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('a file in the builder', () => {
	it('shows under its row what students will read about it', async () => {
		await renderModules(
			outline([
				unit({
					items: [
						item({
							item_type: 'File',
							lesson: null,
							file: 'CFL-1',
							title: 'Reading list',
							description: 'Chapters 1-3, before Tuesday.',
						}),
					],
				}),
			]),
		)

		expect(screen.getByText('Chapters 1-3, before Tuesday.')).toBeInTheDocument()
		// Still named by its title alone.
		expect(screen.getByRole('button', { name: 'More for Reading list' })).toBeInTheDocument()
	})
})

describe('the module builder', () => {
	it('renders a sub-header as a heading rather than as a thing to open', async () => {
		// It names the rows under it and points at nothing, so it gets no type
		// line -- the way Canvas renders a text header.
		await renderModules(
			outline([
				unit({
					items: [
						item({ name: 'CMI-1', item_type: 'Sub-header', title: 'Course Materials' }),
						item({ name: 'CMI-2', title: 'Lecture 1' }),
					],
				}),
			]),
		)

		expect(screen.getByText('Course Materials')).toBeInTheDocument()
		// The lesson says what it is; the sub-header does not, because there is
		// nothing behind it to be.
		expect(screen.getByText('Lesson')).toBeInTheDocument()
		expect(screen.queryByText('Sub-header')).toBeNull()
	})

	it('indents an item, which is a save and not just a margin', async () => {
		await renderModules(outline([unit({ items: [item()] })]))

		await choose('More for Lecture 1', 'Indent')

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.syllabus.save_item')
		expect(args?.item).toBe('CMI-00001')
		expect(args?.values).toMatchObject({ indent: 1 })
	})

	it('will not outdent an item that is already flush left', async () => {
		await renderModules(outline([unit({ items: [item()] })]))

		await userEvent.click(screen.getByRole('button', { name: 'More for Lecture 1' }))

		expect(await screen.findByRole('menuitem', { name: 'Outdent' })).toHaveAttribute(
			'aria-disabled',
			'true',
		)
	})

	it('publishes one item at a time, without touching the module round it', async () => {
		// The point of a per-item state: a lesson can be drafted inside a
		// module students are already working through.
		await renderModules(outline([unit({ items: [item()] })]))

		expect(
			screen.getByRole('button', { name: 'Unpublish module Week 1' }),
		).toBeInTheDocument()

		await userEvent.click(screen.getByRole('button', { name: 'Unpublish Lecture 1' }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.syllabus.save_item')
		expect(args?.values).toMatchObject({ published: 0 })
	})

	it('says which way an unpublished item goes', async () => {
		await renderModules(outline([unit({ items: [item({ published: 0 })] })]))

		expect(screen.getByRole('button', { name: 'Publish Lecture 1' })).toBeInTheDocument()
	})

	it('folds every module shut without losing the modules', async () => {
		await renderModules(
			outline([unit({ items: [item()] }), unit({ name: 'CM-2', title: 'Week 2' })]),
		)

		expect(screen.getByText('Lecture 1')).toBeInTheDocument()

		await userEvent.click(screen.getByRole('button', { name: 'Collapse all' }))

		expect(screen.queryByText('Lecture 1')).toBeNull()
		expect(screen.getByText('Week 1')).toBeInTheDocument()
		expect(screen.getByText('Week 2')).toBeInTheDocument()

		await userEvent.click(screen.getByRole('button', { name: 'Expand all' }))
		expect(screen.getByText('Lecture 1')).toBeInTheDocument()
	})

	it('keeps a way to reorder that is not dragging', async () => {
		// `useDragOrder` says it in its own docstring: native drag and drop
		// cannot be driven from a keyboard, so the move controls stay. They
		// moved into the menu; they did not go away.
		await renderModules(
			outline([unit(), unit({ name: 'CM-2', title: 'Week 2', position: 1 })]),
		)

		await choose('More for Week 1', 'Move down')

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.syllabus.reorder')
		expect(args?.order).toEqual(['CM-2', 'CM-00001'])
	})

	it('cannot move the first module up', async () => {
		await renderModules(
			outline([unit(), unit({ name: 'CM-2', title: 'Week 2', position: 1 })]),
		)

		await userEvent.click(screen.getByRole('button', { name: 'More for Week 1' }))

		expect(await screen.findByRole('menuitem', { name: 'Move up' })).toHaveAttribute(
			'aria-disabled',
			'true',
		)
	})

	it('shows what holds a module shut, in the words a teacher chose', async () => {
		// Prerequisites are stored as names and were picked by title, so they
		// are shown by title.
		await renderModules(
			outline([
				unit(),
				unit({
					name: 'CM-2',
					title: 'Week 2',
					prerequisites: ['CM-00001'],
					require_sequential_progress: 1,
					unlock_at: '2026-10-01T09:00:00',
				}),
			]),
		)

		expect(screen.getByText('After Week 1')).toBeInTheDocument()
		expect(screen.getByText('In order')).toBeInTheDocument()
		expect(screen.getByText(/Unlocks 2026-10-01/)).toBeInTheDocument()
	})

	it('says a module is empty rather than showing nothing at all', async () => {
		await renderModules(outline([unit()]))

		expect(screen.getByText('Nothing in this module yet.')).toBeInTheDocument()
	})
})

describe('editing an item already in a module', () => {
	it('opens where the item sits, with what it already says', async () => {
		const data = outline([
			unit({ items: [item({ completion_requirement: 'Score at least', min_score: 70 })] }),
		])
		data.choices.completion_rules = [...data.choices.completion_rules, 'Score at least']
		await renderModules(data)

		await choose('More for Lecture 1', 'Edit')

		expect(screen.getByLabelText('Title')).toHaveValue('Lecture 1')
		expect(screen.getByLabelText(/What counts as done/)).toHaveValue('Score at least')
		expect(screen.getByLabelText('Minimum score')).toHaveValue(70)
		// What it points at is said, not offered -- see ItemEditForm for why.
		expect(screen.getByText(/add that as a new item/)).toBeInTheDocument()
	})

	it('saves the change to the same item, and leaves what it points at alone', async () => {
		await renderModules(outline([unit({ items: [item()] })]))
		await choose('More for Lecture 1', 'Edit')

		const title = screen.getByLabelText('Title')
		await userEvent.clear(title)
		await userEvent.type(title, 'Lecture 1: Creation')
		await userEvent.selectOptions(screen.getByLabelText(/What counts as done/), 'Mark it done')
		await userEvent.click(screen.getByRole('button', { name: 'Save item' }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]
		expect(path).toBe('sibbcs.api.syllabus.save_item')
		expect(args?.item).toBe('CMI-00001')
		expect(args?.module).toBe('CM-00001')
		// No item_type and no lesson: an edit cannot move students' progress
		// onto something they never opened.
		expect(args?.values).toEqual({
			title: 'Lecture 1: Creation',
			completion_requirement: 'Mark it done',
		})
	})

	it('lets a link be pointed somewhere else', async () => {
		await renderModules(
			outline([
				unit({
					items: [
						item({
							item_type: 'URL',
							title: 'Reading',
							lesson: null,
							url: 'https://old.example.org',
						}),
					],
				}),
			]),
		)
		await choose('More for Reading', 'Edit')

		const link = screen.getByLabelText('Link')
		expect(link).toHaveValue('https://old.example.org')
		await userEvent.clear(link)
		await userEvent.type(link, 'https://www.bible.com')
		await userEvent.click(screen.getByRole('button', { name: 'Save item' }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		expect(post.mock.calls[0][1]?.values).toMatchObject({ url: 'https://www.bible.com' })
	})

	it('gives a sub-header only its title to change', async () => {
		await renderModules(
			outline([
				unit({
					items: [item({ item_type: 'Sub-header', title: 'Course Materials', lesson: null })],
				}),
			]),
		)
		await choose('More for Course Materials', 'Edit')

		expect(screen.getByLabelText('Title')).toHaveValue('Course Materials')
		expect(screen.queryByLabelText(/What counts as done/)).toBeNull()
	})

	it('closes on Cancel without saving anything', async () => {
		await renderModules(outline([unit({ items: [item()] })]))
		await choose('More for Lecture 1', 'Edit')

		await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

		expect(screen.queryByRole('button', { name: 'Save item' })).toBeNull()
		expect(post).not.toHaveBeenCalled()
	})
})

describe('adding an item', () => {
	// The title comes from the content chosen, so a teacher does not retype
	// what the lesson is already called -- and an item never ends up
	// "(untitled)" because the box was left empty.

	const openTheForm = () =>
		userEvent.click(screen.getByRole('button', { name: 'Add an item to Week 1' }))

	it('takes its title from the content chosen', async () => {
		await renderModules(outline([unit()]))
		await openTheForm()

		await userEvent.selectOptions(screen.getByLabelText(/Which one/), 'LES-1')

		expect(screen.getByLabelText('Title')).toHaveValue('Lecture 1')
	})

	it('keeps a title the teacher typed first', async () => {
		await renderModules(outline([unit()]))
		await openTheForm()

		await userEvent.type(screen.getByLabelText('Title'), 'Reading for Monday')
		await userEvent.selectOptions(screen.getByLabelText(/Which one/), 'LES-1')

		expect(screen.getByLabelText('Title')).toHaveValue('Reading for Monday')
	})

	it('replaces a copied title when the choice changes', async () => {
		const data = outline([unit()])
		data.choices.lessons = [
			...data.choices.lessons,
			{ name: 'LES-2', title: 'Lecture 2', chapter: 'CH-1' },
		]
		await renderModules(data)
		await openTheForm()

		await userEvent.selectOptions(screen.getByLabelText(/Which one/), 'LES-1')
		await userEvent.selectOptions(screen.getByLabelText(/Which one/), 'LES-2')

		expect(screen.getByLabelText('Title')).toHaveValue('Lecture 2')
	})

	it('saves the content title even when the box was emptied', async () => {
		await renderModules(outline([unit()]))
		await openTheForm()

		await userEvent.selectOptions(screen.getByLabelText(/Which one/), 'LES-1')
		await userEvent.clear(screen.getByLabelText('Title'))
		await userEvent.click(screen.getByRole('button', { name: 'Add' }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		expect(post.mock.calls[0][1]?.values).toMatchObject({
			item_type: 'Lesson',
			lesson: 'LES-1',
			title: 'Lecture 1',
		})
	})
})
