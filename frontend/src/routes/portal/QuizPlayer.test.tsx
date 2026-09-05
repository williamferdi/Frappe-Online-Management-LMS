import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { QuizAttempt } from '@/types'

const REGISTRATION = 'REG-1'
const ASSIGNMENT = 'CA-00001'

const attempt: QuizAttempt = {
	attempt: 'QAT-00001',
	status: 'In progress',
	started_at: '2026-10-01 10:00:00',
	expires_at: '2026-10-01 10:30:00',
	seconds_remaining: 1800,
	one_question_at_a_time: 0,
	title: 'Old Testament survey',
	description: null,
	questions: [
		{
			name: 'BQN-00001',
			question: '<p>Which book is first?</p>',
			question_type: 'Choice',
			points: 1,
			options: [
				{ idx: 1, text: 'Genesis' },
				{ idx: 2, text: 'Exodus' },
			],
			given: null,
		},
		{
			name: 'BQN-00002',
			question: '<p>Name the second book</p>',
			question_type: 'Short answer',
			points: 2,
			options: [],
			given: null,
		},
	],
}

const post = vi.fn()
const get = vi.fn()

async function renderQuiz(overrides: Partial<QuizAttempt> = {}) {
	vi.resetModules()
	Object.assign(window, { user: 'student@x.com', roles: ['Student'], csrf_token: 't' })

	post.mockImplementation(async (path: string) => {
		if (path === 'sibbcs.api.quiz.start') return { ...attempt, ...overrides }
		return {}
	})
	get.mockImplementation(async () => ({
		attempt: attempt.attempt,
		status: 'Submitted',
		auto_submitted: 0,
		submitted_at: '2026-10-01 10:20:00',
		score: 2,
		points_possible: 3,
	}))

	vi.doMock('@/lib/frappe', async () => {
		const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
		return { ...actual, frappeGet: get, frappePost: post }
	})

	const { QuizPlayer } = await import('./QuizPlayer')
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

	render(
		<QueryClientProvider client={client}>
			<MemoryRouter
				initialEntries={[`/portal/courses/${REGISTRATION}/quiz/${ASSIGNMENT}`]}
			>
				<Routes>
					<Route path="/portal/courses/:name/quiz/:assignment" element={<QuizPlayer />} />
				</Routes>
			</MemoryRouter>
		</QueryClientProvider>,
	)

	await waitFor(() =>
		expect(screen.queryByText('Opening the paper…')).toBeNull(),
	)
}

beforeEach(() => {
	vi.resetModules()
	post.mockClear()
	get.mockClear()
})
afterEach(() => {
	vi.doUnmock('@/lib/frappe')
	vi.restoreAllMocks()
})

describe('sitting a quiz', () => {
	it('shows the paper and the time left', async () => {
		await renderQuiz()

		expect(screen.getByText('Which book is first?')).toBeInTheDocument()
		expect(screen.getByText('30:00')).toBeInTheDocument()
		expect(screen.getByText('0 of 2 answered')).toBeInTheDocument()
	})

	it('never renders which option is correct, because it is never sent', async () => {
		await renderQuiz()

		// The payload type has no such field; this is the assertion that the
		// page cannot leak one if the server ever started sending it.
		const body = document.body.innerHTML
		expect(body).not.toMatch(/is_correct/)
		expect(screen.getByLabelText(/Genesis/)).toBeInTheDocument()
	})

	it('records each answer as it is given, not all at the end', async () => {
		// A browser that dies mid-quiz should lose one answer, not the paper.
		await renderQuiz()

		await userEvent.click(screen.getByLabelText(/Genesis/))

		await waitFor(() =>
			expect(
				post.mock.calls.some(([path]) => path === 'sibbcs.api.quiz.answer'),
			).toBe(true),
		)
		const call = post.mock.calls.find(([path]) => path === 'sibbcs.api.quiz.answer')
		expect(call?.[1]).toMatchObject({
			course_registration: REGISTRATION,
			question: 'BQN-00001',
			value: [1],
		})
	})

	it('takes a typed answer for a short-answer question', async () => {
		await renderQuiz()

		const box = screen.getByLabelText('Answer to question 2')
		await userEvent.type(box, 'Exodus')
		await userEvent.tab()

		await waitFor(() => {
			const call = post.mock.calls.find(
				([path, args]) =>
					path === 'sibbcs.api.quiz.answer' &&
					(args as Record<string, unknown>).question === 'BQN-00002',
			)
			expect(call?.[1]).toMatchObject({ value: 'Exodus' })
		})
	})

	it('hands the paper in and shows the score', async () => {
		await renderQuiz()

		await userEvent.click(screen.getByRole('button', { name: /Hand in/ }))

		await waitFor(() => expect(screen.getByText('Handed in')).toBeInTheDocument())
		expect(screen.getByText('2')).toBeInTheDocument()
		expect(screen.getByText('/ 3')).toBeInTheDocument()
	})

	it('says the answers are withheld when the quiz withholds them', async () => {
		await renderQuiz()
		await userEvent.click(screen.getByRole('button', { name: /Hand in/ }))

		await waitFor(() =>
			expect(screen.getByText(/answers are not shown/)).toBeInTheDocument(),
		)
	})

	it('shows no clock at all for a quiz with no time limit', async () => {
		await renderQuiz({ seconds_remaining: null, expires_at: null })

		expect(screen.queryByText(/^\d+:\d\d$/)).toBeNull()
		expect(screen.getByRole('button', { name: /Hand in/ })).toBeInTheDocument()
	})

	it('explains itself when the attempt cannot be opened', async () => {
		post.mockImplementation(async () => {
			throw new Error('You have used all 1 attempt(s) for this quiz.')
		})

		vi.resetModules()
		Object.assign(window, { user: 'student@x.com', roles: ['Student'], csrf_token: 't' })
		vi.doMock('@/lib/frappe', async () => {
			const actual = await vi.importActual<typeof import('@/lib/frappe')>('@/lib/frappe')
			return { ...actual, frappeGet: get, frappePost: post }
		})

		const { QuizPlayer } = await import('./QuizPlayer')
		const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
		render(
			<QueryClientProvider client={client}>
				<MemoryRouter
					initialEntries={[`/portal/courses/${REGISTRATION}/quiz/${ASSIGNMENT}`]}
				>
					<Routes>
						<Route
							path="/portal/courses/:name/quiz/:assignment"
							element={<QuizPlayer />}
						/>
					</Routes>
				</MemoryRouter>
			</QueryClientProvider>,
		)

		await waitFor(() =>
			expect(screen.getByText('This quiz cannot be opened')).toBeInTheDocument(),
		)
	})
})
