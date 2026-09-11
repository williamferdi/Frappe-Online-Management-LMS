import { describe, expect, it } from 'vitest'

import { cleanPaste, linkAddress } from './editing'

describe('pasting into a page', () => {
	it('keeps what Word meant and drops how Word said it', () => {
		expect(
			cleanPaste(
				'<p class="MsoNormal" style="margin-bottom:0cm"><b><span style="font-family:Calibri">Week one</span></b><o:p></o:p></p>',
			),
		).toBe('<p><b>Week one</b></p>')
	})

	it('does not turn a whole Google Doc bold', () => {
		// Docs wraps the clipboard in <b id="docs-internal-guid-…"> and says its
		// real bold and italic with styles.
		expect(
			cleanPaste(
				'<meta charset="utf-8"><b style="font-weight:normal;" id="docs-internal-guid-1a2b3c"><p dir="ltr" style="line-height:1.38"><span style="font-size:11pt;font-weight:700;">Genesis</span><span style="font-size:11pt;"> and </span><span style="font-size:11pt;font-style:italic;">Exodus</span></p></b>',
			),
		).toBe('<p><strong>Genesis</strong> and <em>Exodus</em></p>')
	})

	it('files a pasted title under the page title', () => {
		expect(cleanPaste('<h1>Syllabus</h1><h6>Small print</h6>')).toBe(
			'<h2>Syllabus</h2><h4>Small print</h4>',
		)
	})

	it('lets nothing through that runs, loads, or points somewhere unsafe', () => {
		expect(
			cleanPaste(
				'<p>Hi<script>alert(1)</script><img src="file:///C:/notes.png" onerror="alert(2)"></p><a href="javascript:alert(3)" onclick="alert(4)">there</a><iframe src="https://evil.example"></iframe>',
			),
		).toBe('<p>Hi</p><a>there</a>')
	})

	it('keeps lists, quotes and links as they were', () => {
		const kept =
			'<ul><li>One</li><li>Two</li></ul><blockquote>In the beginning</blockquote><p><a href="https://www.bible.com">Read</a></p>'
		expect(cleanPaste(kept)).toBe(kept)
	})
})

describe('the address a link goes to', () => {
	it.each([
		['https://www.bible.com/bible/1/GEN.1', 'https://www.bible.com/bible/1/GEN.1'],
		['http://old.example.org', 'http://old.example.org'],
		// What people actually type.
		['www.bible.com', 'https://www.bible.com'],
		['bible.com/gen', 'https://bible.com/gen'],
		['  www.bible.com  ', 'https://www.bible.com'],
		['registrar@sibbc.org', 'mailto:registrar@sibbc.org'],
		['mailto:registrar@sibbc.org', 'mailto:registrar@sibbc.org'],
		// Somewhere on this site.
		['/portal/courses', '/portal/courses'],
	])('takes %j as %j', (typed, address) => {
		expect(linkAddress(typed)).toBe(address)
	})

	it.each([
		'',
		'notes',
		'two words',
		'javascript:alert(1)',
		'data:text/html,<script>alert(1)</script>',
		'//evil.example',
		'mailto:nobody',
	])('refuses %j', (typed) => {
		expect(linkAddress(typed)).toBeNull()
	})
})
