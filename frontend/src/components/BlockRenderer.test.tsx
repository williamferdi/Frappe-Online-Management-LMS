import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { BlockRenderer, type Block } from './BlockRenderer'

describe('rendering a lesson', () => {
	it('renders the block types the estate actually uses', () => {
		// Surveyed on the live site: paragraph, header, list, embed, markdown.
		const blocks: Block[] = [
			{ type: 'header', data: { text: 'Genesis', level: 2 } },
			{ type: 'paragraph', data: { text: 'In the <strong>beginning</strong>.' } },
			{ type: 'list', data: { style: 'unordered', items: ['One', 'Two'] } },
			{ type: 'markdown', data: { text: '<p>From markdown</p>' } },
		]

		render(<BlockRenderer blocks={blocks} />)

		expect(screen.getByRole('heading', { name: 'Genesis' })).toBeInTheDocument()
		expect(screen.getByText('beginning')).toBeInTheDocument()
		expect(screen.getByText('One')).toBeInTheDocument()
		expect(screen.getByText('From markdown')).toBeInTheDocument()
	})

	it('falls back visibly for a block it has never heard of', () => {
		// Block shape is not a contract anybody owns, so the failure to design
		// for is a blank lesson. A lesson degrades; it does not vanish.
		render(
			<BlockRenderer
				blocks={[{ type: 'somethingNew', data: {} }]}
				lmsUrl="/lms/courses/intro"
			/>,
		)

		expect(screen.getByText(/cannot be shown here yet/)).toBeInTheDocument()
		expect(screen.getByRole('link', { name: /Open in the LMS/ })).toHaveAttribute(
			'href',
			'/lms/courses/intro',
		)
	})

	it('says when an exercise was taken out, rather than leaving a hole', () => {
		render(
			<BlockRenderer
				blocks={[{ type: 'paragraph', data: { text: 'Read this' } }]}
				removed={['quiz']}
			/>,
		)

		expect(screen.getByText(/not shown here/)).toBeInTheDocument()
		expect(screen.getByText(/listed in the module instead/)).toBeInTheDocument()
	})

	it('embeds a video only from a service the LMS actually produces', () => {
		const { container } = render(
			<BlockRenderer
				blocks={[
					{
						type: 'embed',
						data: {
							embed: 'https://www.youtube.com/embed/abc123',
							caption: 'A lecture',
						},
					},
				]}
			/>,
		)

		expect(container.querySelector('iframe')).toHaveAttribute(
			'src',
			'https://www.youtube.com/embed/abc123',
		)
	})

	it('refuses to iframe a URL from lesson content it does not recognise', () => {
		// A raw URL out of stored content dropped into `src` is somebody
		// else's page running inside the portal.
		const { container } = render(
			<BlockRenderer
				blocks={[
					{
						type: 'embed',
						data: {
							embed: 'https://evil.example/steal',
							source: 'https://evil.example/steal',
						},
					},
				]}
			/>,
		)

		expect(container.querySelector('iframe')).toBeNull()
		expect(screen.getByText(/embeds something from elsewhere/)).toBeInTheDocument()
	})

	it('says so when a lesson has no content at all', () => {
		// 104 of the 115 lessons on the live site are empty.
		render(<BlockRenderer blocks={[]} />)

		expect(screen.getByText(/no content yet/)).toBeInTheDocument()
	})
})
