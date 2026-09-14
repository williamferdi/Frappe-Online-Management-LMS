/**
 * A Text Editor value without its markup, for the places that cannot draw
 * any: hover text, a one-line preview. Parsed rather than regexed, and a
 * parsed document is inert -- nothing in it loads or runs.
 */
export function plainText(html: string) {
	const text = new DOMParser().parseFromString(html, 'text/html').body.textContent ?? ''
	return text.replace(/\s+/g, ' ').trim()
}
