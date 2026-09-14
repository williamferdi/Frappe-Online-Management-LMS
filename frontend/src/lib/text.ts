// Elements whose end is a break in the reading, so their text is not run into
// the next element's: without this, two paragraphs read "One.Two.".
const BREAKS = 'p, div, li, br, h1, h2, h3, h4, h5, h6, blockquote, tr'

/**
 * A Text Editor value without its markup, for the places that cannot draw
 * any: hover text, a one-line preview. Parsed rather than regexed, and a
 * parsed document is inert -- nothing in it loads or runs.
 */
export function plainText(html: string) {
	const body = new DOMParser().parseFromString(html, 'text/html').body
	body.querySelectorAll(BREAKS).forEach((element) => element.after(' '))
	return (body.textContent ?? '').replace(/\s+/g, ' ').trim()
}
