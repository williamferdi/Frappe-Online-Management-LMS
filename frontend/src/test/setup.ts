import '@testing-library/jest-dom/vitest'

// jsdom implements no media queries at all, so anything reading the colour
// scheme throws on render rather than falling back.
if (!window.matchMedia) {
	window.matchMedia = ((query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addEventListener: () => {},
		removeEventListener: () => {},
		addListener: () => {},
		removeListener: () => {},
		dispatchEvent: () => false,
	})) as typeof window.matchMedia
}
