import { describe, expect, it } from 'vitest'

import { plainText } from './text'

describe('a brief as plain text', () => {
	it('keeps paragraphs apart', () => {
		// The bug this closes: textContent alone ran them together.
		expect(plainText('<p>One.</p><p>Two.</p>')).toBe('One. Two.')
	})

	it('keeps inline formatting inside its sentence', () => {
		expect(plainText('<p>Read <strong>Romans 8</strong>.</p>')).toBe('Read Romans 8.')
	})

	it('reads entities and line breaks as the words they stand for', () => {
		expect(plainText('<p>Genesis&nbsp;1&ndash;3<br>then Exodus</p>')).toBe(
			'Genesis 1–3 then Exodus',
		)
	})

	it('says nothing for an emptied editor', () => {
		expect(plainText('<div class="ql-editor read-mode"><p><br></p></div>')).toBe('')
	})

	it('runs nothing it is given', () => {
		const before = document.title
		expect(plainText('<img src=x onerror="document.title=\'ran\'">Hello')).toBe('Hello')
		expect(document.title).toBe(before)
	})
})
