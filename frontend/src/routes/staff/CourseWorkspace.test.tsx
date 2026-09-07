import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClipboardList, Layers, Percent } from 'lucide-react'

import { TabsContent } from '@/components/ui/tabs'
import { CourseWorkspace, type CourseSection } from './CourseWorkspace'

const SECTIONS: CourseSection[] = [
	{ value: 'scheme', label: 'Grade scheme', icon: Percent },
	{ value: 'assignments', label: 'Assignments', icon: ClipboardList, count: 3 },
	{ value: 'modules', label: 'Modules', icon: Layers },
]

function Harness({ start = 'scheme' }: { start?: string }) {
	const [value, setValue] = useState(start)
	return (
		<CourseWorkspace sections={SECTIONS} value={value} onValueChange={setValue}>
			<TabsContent value="scheme">The weighting</TabsContent>
			<TabsContent value="assignments">The work</TabsContent>
			<TabsContent value="modules">The order</TabsContent>
		</CourseWorkspace>
	)
}

describe('the course workspace', () => {
	it('names its sections so a screen reader knows what the column is', () => {
		render(<Harness />)

		const nav = screen.getByRole('tablist', { name: 'Course sections' })
		expect(nav).toHaveAttribute('aria-orientation', 'vertical')
		expect(screen.getAllByRole('tab')).toHaveLength(3)
	})

	it('shows one panel, the one the section names', () => {
		render(<Harness start="assignments" />)

		expect(screen.getByRole('tab', { name: /Assignments/ })).toHaveAttribute(
			'aria-selected',
			'true',
		)
		expect(screen.getByText('The work')).toBeInTheDocument()
		expect(screen.queryByText('The weighting')).toBeNull()
	})

	it('counts the work beside the section that holds it', () => {
		render(<Harness />)

		expect(screen.getByRole('tab', { name: /Assignments/ })).toHaveTextContent('3')
	})

	it('moves down the column on the arrow that points down it', async () => {
		// A horizontal strip takes left and right; a column has to take the
		// arrows that run along it, or a keyboard cannot get past the first.
		render(<Harness />)

		screen.getByRole('tab', { name: /Grade scheme/ }).focus()
		await userEvent.keyboard('{ArrowDown}')

		expect(screen.getByRole('tab', { name: /Assignments/ })).toHaveAttribute(
			'aria-selected',
			'true',
		)
		expect(screen.getByText('The work')).toBeInTheDocument()
	})

	it('switches section on a click', async () => {
		render(<Harness />)

		await userEvent.click(screen.getByRole('tab', { name: /Modules/ }))

		expect(screen.getByText('The order')).toBeInTheDocument()
	})
})
