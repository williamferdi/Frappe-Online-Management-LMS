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
		// A real-shaped id: every YouTube id is eleven characters, and the
		// renderer now checks that rather than trusting any path on the host.
		const { container } = render(
			<BlockRenderer
				blocks={[
					{
						type: 'embed',
						data: {
							embed: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
							caption: 'A lecture',
						},
					},
				]}
			/>,
		)

		expect(container.querySelector('iframe')).toHaveAttribute(
			'src',
			'https://www.youtube.com/embed/dQw4w9WgXcQ',
		)
	})

	it('plays a video pasted as an ordinary YouTube link', () => {
		// The reported fault. The watch page answers a frame with
		// `X-Frame-Options: SAMEORIGIN`, which the browser draws as
		// "www.youtube.com refused to connect"; what is framed must be the
		// embed address for the same video.
		const { container } = render(
			<BlockRenderer
				blocks={[
					{
						type: 'embed',
						data: { embed: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' },
					},
				]}
			/>,
		)

		expect(container.querySelector('iframe')).toHaveAttribute(
			'src',
			'https://www.youtube.com/embed/dQw4w9WgXcQ',
		)
	})

	it('plays the shape the LMS writes: a bare id in embed, the link in source', () => {
		// Found on production: three of the four embeds hold `embed: 'eLprQT4Eyms'`
		// with the youtu.be link in `source`. The old check refused a bare id, so
		// those lessons showed a notice where the lecture should have been.
		const { container } = render(
			<BlockRenderer
				blocks={[
					{
						type: 'embed',
						data: { embed: 'dQw4w9WgXcQ', source: 'https://youtu.be/dQw4w9WgXcQ' },
					},
				]}
			/>,
		)

		expect(container.querySelector('iframe')).toHaveAttribute(
			'src',
			'https://www.youtube.com/embed/dQw4w9WgXcQ',
		)
	})

	it('does not frame a page on YouTube that is not a video', () => {
		// The old check trusted any path on youtube.com, redirects included.
		const { container } = render(
			<BlockRenderer
				blocks={[
					{
						type: 'embed',
						data: { embed: 'https://www.youtube.com/redirect?q=https://evil.example' },
					},
				]}
			/>,
		)

		expect(container.querySelector('iframe')).toBeNull()
	})

	it('offers no link that is not a web address', () => {
		render(
			<BlockRenderer
				blocks={[
					{
						type: 'embed',
						data: { embed: 'javascript:alert(1)', source: 'javascript:alert(1)' },
					},
				]}
			/>,
		)

		expect(screen.getByText(/embeds something from elsewhere/)).toBeInTheDocument()
		expect(screen.queryByRole('link', { name: 'Open it directly' })).toBeNull()
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
