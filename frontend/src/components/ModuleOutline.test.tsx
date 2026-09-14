import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { ModuleOutline } from './ModuleOutline'
import type { OutlineItem, OutlineModule } from '@/types'

function item(over: Partial<OutlineItem> = {}): OutlineItem {
	return {
		name: 'CMI-1',
		module: 'CM-1',
		item_type: 'Lesson',
		title: 'What Scripture is',
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
		name: 'CM-1',
		title: 'Week One',
		position: 0,
		published: 1,
		unlock_at: null,
		require_sequential_progress: 0,
		prerequisites: [],
		state: { open: true, reason: null },
		complete: false,
		items: [item()],
		...over,
	}
}

function Harness({
	modules,
	canOpen,
	itemHref,
}: {
	modules: OutlineModule[]
	canOpen?: (item: OutlineItem) => boolean
	itemHref?: (item: OutlineItem) => string | null
}) {
	const [open, setOpen] = useState<string | null>(null)
	// A Router because a row that leads somewhere is a `Link`, and one that
	// opens in place is not -- both shapes are rendered from here.
	return (
		<MemoryRouter>
			<ModuleOutline
				modules={modules}
				itemHref={itemHref}
				openItem={open}
				onOpenItem={setOpen}
				canOpen={canOpen}
				renderBody={(row) => <div>Inside {row.title}</div>}
			/>
		</MemoryRouter>
	)
}

describe('a file in the outline', () => {
	it('says what the file is about under its title', () => {
		const reading = item({
			item_type: 'File',
			lesson: null,
			file: 'CFL-1',
			title: 'Reading list',
			description: 'Read chapters 1-3 before Tuesday.',
		})
		render(<Harness modules={[unit({ items: [reading] })]} itemHref={() => '/portal/read'} />)

		expect(screen.getByText('Read chapters 1-3 before Tuesday.')).toBeInTheDocument()
		// Beside the link, not in it, so the link is still named by its title.
		expect(screen.getByRole('link', { name: 'Reading list' })).toBeInTheDocument()
	})
})

describe('the course outline a student meets', () => {
	it('opens a row into whatever the caller puts there', async () => {
		render(<Harness modules={[unit()]} />)

		await userEvent.click(screen.getByRole('button', { name: 'What Scripture is' }))

		expect(screen.getByText('Inside What Scripture is')).toBeInTheDocument()
	})

	it('shuts a locked row for a student and leaves it open for a teacher', async () => {
		// The one real difference between the two screens this serves. A
		// student cannot open what is locked; a teacher checking a module that
		// unlocks next week has to be able to.
		const locked = [
			unit({ items: [item({ locked: true, lock_reason: 'Opens 1 October' })] }),
		]

		const { unmount } = render(
			<Harness modules={locked} canOpen={(row) => !row.locked} />,
		)
		expect(screen.getByRole('button', { name: 'What Scripture is' })).toBeDisabled()
		expect(screen.getByText('Opens 1 October')).toBeInTheDocument()
		unmount()

		render(<Harness modules={locked} />)
		expect(screen.getByRole('button', { name: 'What Scripture is' })).toBeEnabled()
	})

	it('names the row after the row, not after everything printed on it', async () => {
		// The type and the requirement are shown under the title. Folding them
		// into the control would rename it to something nobody would say.
		render(
			<Harness
				modules={[unit({ items: [item({ completion_requirement: 'Mark it done' })] })]}
			/>,
		)

		expect(screen.getByRole('button', { name: 'What Scripture is' })).toBeInTheDocument()
		expect(screen.getByText(/Lesson · Mark it done/)).toBeInTheDocument()
	})

	it('renders a sub-header as a heading with nothing to open', () => {
		render(
			<Harness
				modules={[
					unit({
						items: [
							item({ name: 'CMI-0', item_type: 'Sub-header', title: 'Course Materials' }),
							item(),
						],
					}),
				]}
			/>,
		)

		expect(screen.getByText('Course Materials')).toBeInTheDocument()
		expect(screen.queryByRole('button', { name: 'Course Materials' })).toBeNull()
	})

	it('indents a row under the sub-header that names it', () => {
		render(<Harness modules={[unit({ items: [item({ indent: 2 })] })]} />)

		const row = screen.getByRole('button', { name: 'What Scripture is' }).closest('li')
		// The inline style rather than the computed one: jsdom lays nothing
		// out, so it never resolves a rem to pixels.
		expect(row?.getAttribute('style')).toContain('padding-left: 3.75rem')
	})

	it('says why a module is shut instead of only refusing', () => {
		render(
			<Harness
				modules={[
					unit({ state: { open: false, reason: 'Finish Week One first' } }),
				]}
			/>,
		)

		expect(screen.getByText('Finish Week One first')).toBeInTheDocument()
	})

	it('marks a finished module as finished', () => {
		render(<Harness modules={[unit({ complete: true })]} />)

		expect(screen.getByText('Done')).toBeInTheDocument()
	})

	it('folds a module shut without losing it', async () => {
		render(<Harness modules={[unit()]} />)

		await userEvent.click(screen.getByRole('button', { name: 'Collapse Week One' }))

		expect(screen.queryByRole('button', { name: 'What Scripture is' })).toBeNull()
		expect(screen.getByText('Week One')).toBeInTheDocument()

		await userEvent.click(screen.getByRole('button', { name: 'Expand Week One' }))
		expect(screen.getByRole('button', { name: 'What Scripture is' })).toBeInTheDocument()
	})

	it('leads somewhere when given somewhere to lead', () => {
		// The student's list sends a row to the player. The teacher's preview
		// cannot -- the player is addressed by a registration and a teacher
		// does not have one -- so it opens in place instead.
		render(<Harness modules={[unit()]} itemHref={(row) => `/learn/${row.name}`} />)

		expect(screen.getByRole('link', { name: 'What Scripture is' })).toHaveAttribute(
			'href',
			'/learn/CMI-1',
		)
		expect(screen.queryByRole('button', { name: 'What Scripture is' })).toBeNull()
	})

	it('will not make a locked row into a link', () => {
		// There is no disabled link. Left as a link it could still be followed
		// by keyboard, by middle click, or by copying the address out of it --
		// and the player would only refuse.
		render(
			<Harness
				modules={[unit({ items: [item({ locked: true, lock_reason: 'Not yet' })] })]}
				itemHref={(row) => `/learn/${row.name}`}
				canOpen={(row) => !row.locked}
			/>,
		)

		expect(screen.queryByRole('link', { name: 'What Scripture is' })).toBeNull()
		expect(screen.getByRole('button', { name: 'What Scripture is' })).toBeDisabled()
	})

	it('says a module is empty rather than showing nothing', () => {
		render(<Harness modules={[unit({ items: [] })]} />)

		expect(screen.getByText('Nothing in this module yet.')).toBeInTheDocument()
	})
})
