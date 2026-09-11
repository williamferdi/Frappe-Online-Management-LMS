import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'

import { RichTextEditor } from './RichTextEditor'

/** The editor as a page uses it: a label, and the body held above it. */
function Harness({ initial, onChange }: { initial: string; onChange?: (html: string) => void }) {
	const [value, setValue] = useState(initial)
	return (
		<>
			<span id="body-label">Body</span>
			<RichTextEditor
				id="body"
				labelledBy="body-label"
				value={value}
				onChange={(html) => {
					setValue(html)
					onChange?.(html)
				}}
			/>
		</>
	)
}

// jsdom implements no editing commands, so what is tested here is which
// command the toolbar asks the browser for. Carrying it out is the browser's
// part, and was looked at in a real one.
const exec = vi.fn((_command: string, _ui?: boolean, _value?: string) => true)
const original = document.execCommand

beforeEach(() => {
	exec.mockClear()
	document.execCommand = exec as unknown as typeof document.execCommand
})
afterEach(() => {
	document.execCommand = original
})

const body = () => screen.getByRole('textbox', { name: 'Body' })

/** Chooses part of the text, as somebody dragging across it would. */
function select(node: Node, start: number, end: number) {
	const range = document.createRange()
	range.setStart(node, start)
	range.setEnd(node, end)
	const selection = document.getSelection()!
	selection.removeAllRanges()
	selection.addRange(range)
	document.dispatchEvent(new Event('selectionchange'))
}

describe('the page editor', () => {
	it('loads a stored body without letting anything in it run', () => {
		render(<Harness initial={'<p>Welcome</p><img src="x" onerror="window.ran = true">'} />)

		expect(body()).toContainHTML('<p>Welcome</p>')
		expect(body().innerHTML).not.toContain('onerror')
	})

	it('hands up exactly what the author wrote', () => {
		const changed = vi.fn()
		render(<Harness initial="" onChange={changed} />)

		body().innerHTML = '<p>Week one: <strong>Genesis</strong></p>'
		fireEvent.input(body())

		expect(changed).toHaveBeenLastCalledWith('<p>Week one: <strong>Genesis</strong></p>')
	})

	it('treats a body emptied back to a bare line as empty', () => {
		const changed = vi.fn()
		render(<Harness initial="<p>Gone soon</p>" onChange={changed} />)

		body().innerHTML = '<p><br></p>'
		fireEvent.input(body())

		expect(changed).toHaveBeenLastCalledWith('')
	})

	it('asks the browser for the formatting each button names', async () => {
		render(<Harness initial="<p>Genesis</p>" />)

		await userEvent.click(screen.getByRole('button', { name: 'Bold' }))
		expect(exec).toHaveBeenCalledWith('bold', false, undefined)

		await userEvent.click(screen.getByRole('button', { name: 'Heading' }))
		expect(exec).toHaveBeenCalledWith('formatBlock', false, '<h2>')

		await userEvent.click(screen.getByRole('button', { name: 'Numbered list' }))
		expect(exec).toHaveBeenCalledWith('insertOrderedList', false, undefined)
	})

	it('is one stop on the tab order, and the arrow keys move along it', async () => {
		render(<Harness initial="" />)
		const toolbar = screen.getByRole('toolbar', { name: 'Formatting' })
		const buttons = within(toolbar).getAllByRole('button')

		expect(buttons.filter((button) => button.tabIndex === 0)).toHaveLength(1)

		act(() => buttons[0]!.focus())
		await userEvent.keyboard('{ArrowRight}')
		expect(document.activeElement).toBe(within(toolbar).getByRole('button', { name: 'Italic' }))

		await userEvent.keyboard('{End}')
		expect(document.activeElement).toBe(
			within(toolbar).getByRole('button', { name: 'Edit as HTML' }),
		)
	})

	it('cleans what is pasted from Word before it goes in', () => {
		render(<Harness initial="" />)

		fireEvent.paste(body(), {
			clipboardData: {
				getData: (type: string) =>
					type === 'text/html'
						? '<p class="MsoNormal" style="color:red"><span style="font-weight:700">Hi</span></p>'
						: 'Hi',
			},
		})

		expect(exec).toHaveBeenCalledWith('insertHTML', false, '<p><strong>Hi</strong></p>')
	})

	it('links the chosen words to an address it has checked', async () => {
		render(<Harness initial="<p>Read Genesis one</p>" />)
		act(() => select(body().querySelector('p')!.firstChild!, 5, 12))

		await userEvent.click(screen.getByRole('button', { name: 'Link' }))
		await userEvent.type(screen.getByLabelText('Link address'), 'www.bible.com{Enter}')

		expect(exec).toHaveBeenCalledWith('createLink', false, 'https://www.bible.com')
	})

	it('refuses an address that goes nowhere, and says why', async () => {
		render(<Harness initial="<p>Read Genesis one</p>" />)
		act(() => select(body().querySelector('p')!.firstChild!, 5, 12))

		await userEvent.click(screen.getByRole('button', { name: 'Link' }))
		await userEvent.type(screen.getByLabelText('Link address'), 'notes{Enter}')

		expect(screen.getByRole('alert')).toHaveTextContent('not a web address')
		expect(exec).not.toHaveBeenCalledWith('createLink', expect.anything(), expect.anything())
	})

	it('links the words just chosen, even before the browser has said so', async () => {
		// `selectionchange` is queued behind input, so a quick click can land
		// before it. Found in Chromium: Link wrapped the old caret position. So
		// the toolbar reads the selection itself -- chosen here with no event.
		render(<Harness initial="<p>Read Genesis one</p>" />)
		const text = body().querySelector('p')!.firstChild!
		const range = document.createRange()
		range.setStart(text, 5)
		range.setEnd(text, 12)
		document.getSelection()!.removeAllRanges()
		document.getSelection()!.addRange(range)

		await userEvent.click(screen.getByRole('button', { name: 'Link' }))
		await userEvent.type(screen.getByLabelText('Link address'), 'www.bible.com{Enter}')

		expect(exec).toHaveBeenCalledWith('createLink', false, 'https://www.bible.com')
		expect(exec).not.toHaveBeenCalledWith('insertHTML', expect.anything(), expect.anything())
	})

	it('starts an empty page inside a paragraph, so its first line is one', () => {
		// Otherwise the first line typed is bare text beside the <p>s that
		// follow it -- `Line one<p>Line two</p>`, as Chromium wrote it.
		render(<Harness initial="" />)

		fireEvent.focusIn(body())

		expect(body().innerHTML).toBe('<p><br></p>')
		expect(exec).toHaveBeenCalledWith('defaultParagraphSeparator', false, 'p')
	})

	it('goes to HTML and back without losing a word', async () => {
		render(<Harness initial="<p>One</p>" />)

		await userEvent.click(screen.getByRole('button', { name: 'Edit as HTML' }))
		expect(body()).toHaveValue('<p>One</p>')
		// Formatting buttons would act on text that is not on screen.
		expect(screen.getByRole('button', { name: 'Bold' })).toBeDisabled()

		fireEvent.change(body(), { target: { value: '<p>Two</p>' } })
		await userEvent.click(screen.getByRole('button', { name: 'Edit as HTML' }))

		expect(body()).toContainHTML('<p>Two</p>')
	})
})
