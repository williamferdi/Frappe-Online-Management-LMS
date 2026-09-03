import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import { Donut } from './Donut'

const PROGRAMMES = [
	{ label: 'M.Div', count: 98 },
	{ label: 'MA CS', count: 2 },
	{ label: 'GDCS', count: 1 },
	{ label: 'B.Th', count: 0 },
]

describe('a donut', () => {
	it('puts the total in the middle, where the eye lands first', () => {
		render(<Donut title="Programme" slices={PROGRAMMES} />)

		expect(screen.getByText('101')).toBeInTheDocument()
		expect(screen.getByText('Total')).toBeInTheDocument()
	})

	it('lists every category with its count, including the empty one', () => {
		// "B.Th 0" is a fact worth seeing, and the legend is what makes the
		// identity of a slice something other than its colour.
		render(<Donut title="Programme" slices={PROGRAMMES} />)

		const legend = screen.getByRole('list')
		for (const slice of PROGRAMMES) {
			expect(within(legend).getByText(slice.label)).toBeInTheDocument()
		}
		expect(within(legend).getByText('0')).toBeInTheDocument()
	})

	it('draws an arc only for a category somebody is in', () => {
		const { container } = render(<Donut title="Programme" slices={PROGRAMMES} />)

		// One track plus three arcs; the empty programme draws nothing.
		expect(container.querySelectorAll('circle')).toHaveLength(4)
	})

	it('says the whole breakdown to a screen reader', () => {
		render(<Donut title="Programme" slices={PROGRAMMES} />)

		expect(
			screen.getByRole('img', { name: /Programme: M\.Div 98, MA CS 2, GDCS 1, B\.Th 0/ }),
		).toBeInTheDocument()
	})

	it('keeps a category on its own colour however many are drawn', () => {
		// Colour follows the entity, never its rank: a programme emptying out
		// must not repaint the others.
		const { container: full } = render(<Donut title="A" slices={PROGRAMMES} />)
		const { container: fewer } = render(
			<Donut
				title="B"
				slices={[{ label: 'M.Div', count: 98 }, { label: 'MA CS', count: 0 }, { label: 'GDCS', count: 1 }]}
			/>,
		)

		const colourOf = (container: HTMLElement, label: string) =>
			(
				within(container).getByText(label).previousElementSibling as HTMLElement
			).style.background

		expect(colourOf(fewer, 'GDCS')).toBe(colourOf(full, 'GDCS'))
	})

	it('reads a percentage out of the arc for a pointer', () => {
		render(<Donut title="Gender" slices={[{ label: 'Male', count: 83 }, { label: 'Female', count: 18 }]} />)

		expect(screen.getByText('Male: 83 of 101 (82%)')).toBeInTheDocument()
	})

	it('draws a ring even when the roll is empty', () => {
		const { container } = render(
			<Donut title="Transfer" slices={[{ label: 'Yes', count: 0 }, { label: 'No', count: 0 }]} />,
		)

		expect(container.querySelectorAll('circle')).toHaveLength(1)
		// The centre and both legend rows all read nought, which is the point.
		expect(within(container).getAllByText('0')).toHaveLength(3)
	})
})
