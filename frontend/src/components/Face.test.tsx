import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { Face } from './Face'

describe('a face in a list', () => {
	it('shows the photograph when there is one', () => {
		const { container } = render(
			<Face name="Beula Patricia" photo="/private/files/APP-2026-00014-photo.jpeg" />,
		)

		const image = container.querySelector('img')
		expect(image).toHaveAttribute('src', '/private/files/APP-2026-00014-photo.jpeg')
	})

	it('shows initials when nobody sent a photograph', () => {
		const { container } = render(<Face name="Gandham Vijay Kumar" photo={null} />)

		expect(container.querySelector('img')).toBeNull()
		expect(screen.getByText('GV')).toBeInTheDocument()
	})

	it('falls back to initials rather than a broken frame', () => {
		// A private file the reader may not fetch, or one that has been deleted.
		const { container } = render(<Face name="Beula Patricia" photo="/private/files/gone.jpg" />)

		fireEvent.error(container.querySelector('img') as HTMLImageElement)

		expect(container.querySelector('img')).toBeNull()
		expect(screen.getByText('BP')).toBeInTheDocument()
	})
})
