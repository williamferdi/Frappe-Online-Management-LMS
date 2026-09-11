import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const WATCH = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
const EMBED = 'https://www.youtube.com/embed/dQw4w9WgXcQ'

const post = vi.fn(async (_path: string, _args?: Record<string, unknown>) => ({
	lesson: 'LES-1',
}))

async function renderEditor() {
	vi.resetModules()
	Object.assign(window, { user: 'faculty@x.com', roles: ['Faculty'], csrf_token: 't' })

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappePost: post }
	})

	const { LessonEditor } = await import('./LessonEditor')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	return render(
		<QueryClientProvider client={client}>
			<LessonEditor
				offering="THST601-TERM-A"
				chapter="CH-1"
				initialTitle="Creation"
				initialBlocks={[{ type: 'embed', data: { embed: '', caption: '' } }]}
				blockTypes={['paragraph', 'embed']}
				onDone={() => {}}
			/>
		</QueryClientProvider>,
	)
}

beforeEach(() => {
	vi.resetModules()
	post.mockClear()
})
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('a video in a lesson', () => {
	it('plays the link from the address bar in the preview, before anything is saved', async () => {
		const { container } = await renderEditor()

		await userEvent.type(screen.getByLabelText('Video address 1'), WATCH)

		expect(container.querySelector('iframe')).toHaveAttribute('src', EMBED)
		expect(screen.getByText(/it will play in the lesson/)).toBeInTheDocument()
	})

	it('saves the address that plays, and keeps the one that was pasted', async () => {
		await renderEditor()

		await userEvent.type(screen.getByLabelText('Video address 1'), WATCH)
		await userEvent.click(screen.getByRole('button', { name: 'Save lesson' }))

		await waitFor(() => expect(post).toHaveBeenCalled())
		const [path, args] = post.mock.calls[0]!
		expect(path).toBe('sibbcs.api.content.save_lesson')
		const blocks = (args as { blocks: { data: Record<string, unknown> }[] }).blocks
		expect(blocks[0]!.data).toMatchObject({ embed: EMBED, source: WATCH, service: 'youtube' })
	})

	it('says so when a link will not play, rather than leaving it for a student to find', async () => {
		const { container } = await renderEditor()

		await userEvent.type(
			screen.getByLabelText('Video address 1'),
			'https://example.com/lecture.mp4',
		)

		expect(screen.getByText(/Not a YouTube or Vimeo video link/)).toBeInTheDocument()
		expect(container.querySelector('iframe')).toBeNull()
	})
})
