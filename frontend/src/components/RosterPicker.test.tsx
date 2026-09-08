import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { RosterPicker, type RosterEntry } from './RosterPicker'

const ROSTER: RosterEntry[] = [
	{ name: 'REG-1', student_name: 'Beula Patricia' },
	{ name: 'REG-2', student_name: 'Ruth Demo' },
	{ name: 'REG-3', student_name: 'Vignesh Kumar' },
]

function Harness({
	roster = ROSTER,
	onChange = () => {},
}: {
	roster?: RosterEntry[]
	onChange?: (value: string | null) => void
}) {
	const [value, setValue] = useState<string | null>(null)
	return (
		<RosterPicker
			roster={roster}
			value={value}
			onChange={(next) => {
				setValue(next)
				onChange(next)
			}}
		/>
	)
}

const picker = () => screen.getByRole('combobox', { name: 'Seen as' })

describe('choosing whose view to look at', () => {
	it('narrows the list as a name is typed', async () => {
		render(<Harness />)

		await userEvent.click(picker())
		expect(screen.getAllByRole('option')).toHaveLength(4) // three people, and nobody

		await userEvent.type(picker(), 'ruth')

		const options = screen.getAllByRole('option')
		expect(options).toHaveLength(2)
		expect(within(options[1]).getByText('Ruth Demo')).toBeInTheDocument()
	})

	it('matches the middle of a name, not only the beginning', async () => {
		// The browser's own type-ahead on a `<select>` matches from the start,
		// which is no use to anybody who knows the surname.
		render(<Harness />)

		await userEvent.click(picker())
		await userEvent.type(picker(), 'kumar')

		expect(screen.getAllByRole('option')).toHaveLength(2)
		expect(screen.getByText('Vignesh Kumar')).toBeInTheDocument()
	})

	it('can be driven entirely from the keyboard', async () => {
		const onChange = vi.fn()
		render(<Harness onChange={onChange} />)

		await userEvent.click(picker())
		await userEvent.keyboard('{ArrowDown}{ArrowDown}{Enter}')

		expect(onChange).toHaveBeenCalledWith('REG-2')
		expect(picker()).toHaveValue('Ruth Demo')
	})

	it('says which option the keyboard is on', async () => {
		// Without `aria-activedescendant` a screen reader follows the caret in
		// the box and never hears the list move.
		render(<Harness />)

		await userEvent.click(picker())
		await userEvent.keyboard('{ArrowDown}')

		const active = picker().getAttribute('aria-activedescendant')
		expect(active).toBeTruthy()
		expect(document.getElementById(active!)).toHaveTextContent('Beula Patricia')
	})

	it('leaves the choice alone when Escape is pressed', async () => {
		const onChange = vi.fn()
		render(<Harness onChange={onChange} />)

		await userEvent.click(picker())
		await userEvent.keyboard('{ArrowDown}{Enter}')
		expect(picker()).toHaveValue('Beula Patricia')

		await userEvent.click(picker())
		await userEvent.type(picker(), 'ruth')
		await userEvent.keyboard('{Escape}')

		expect(picker()).toHaveValue('Beula Patricia')
		expect(onChange).toHaveBeenCalledTimes(1)
	})

	it('always offers the way back to nobody in particular', async () => {
		// Filtered away, somebody who has typed a name could not get back to
		// the view of a student who has just arrived.
		const onChange = vi.fn()
		render(<Harness onChange={onChange} />)

		await userEvent.click(picker())
		await userEvent.type(picker(), 'ruth')

		const first = screen.getAllByRole('option')[0]
		expect(first).toHaveTextContent('A student who has just arrived')

		await userEvent.click(first)
		expect(onChange).toHaveBeenLastCalledWith(null)
	})

	it('says when a name matches nobody', async () => {
		render(<Harness />)

		await userEvent.click(picker())
		await userEvent.type(picker(), 'zzz')

		expect(screen.getByText('Nobody on this course by that name.')).toBeInTheDocument()
	})

	it('does not render two hundred names at once', async () => {
		// A list that long is not read, it is scrolled past. The count says so
		// rather than the browser quietly carrying the whole cohort.
		const cohort = Array.from({ length: 200 }, (_, index) => ({
			name: `REG-${index}`,
			student_name: `Student ${index}`,
		}))
		render(<Harness roster={cohort} />)

		await userEvent.click(picker())

		expect(screen.getAllByRole('option').length).toBeLessThan(60)
		expect(screen.getByText(/150 more/)).toBeInTheDocument()
	})

	it('shows something for a registration with no name on it yet', async () => {
		render(<Harness roster={[{ name: 'REG-9', student_name: null }]} />)

		await userEvent.click(picker())

		expect(screen.getByText('REG-9')).toBeInTheDocument()
	})
})
