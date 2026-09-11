import { describe, expect, it } from 'vitest'

import { readVideo } from './video'

const ID = 'dQw4w9WgXcQ'
const EMBED = `https://www.youtube.com/embed/${ID}`

describe('reading a video link', () => {
	it.each([
		// The address bar -- the one that was refusing to connect.
		`https://www.youtube.com/watch?v=${ID}`,
		`https://www.youtube.com/watch?v=${ID}&list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG`,
		`https://m.youtube.com/watch?v=${ID}`,
		`http://youtube.com/watch?v=${ID}`,
		// The Share button, with the tracking tag it adds.
		`https://youtu.be/${ID}?si=Ab12Cd34Ef56Gh78`,
		`https://www.youtube.com/shorts/${ID}`,
		`https://www.youtube.com/live/${ID}`,
		// Already right, and must stay right.
		EMBED,
		// Pasted with the space a copy often brings with it.
		`  https://www.youtube.com/watch?v=${ID}  `,
	])('plays %s', (link) => {
		expect(readVideo(link)).toEqual({ service: 'youtube', embed: EMBED })
	})

	it('keeps the moment a link was shared from', () => {
		expect(readVideo(`https://youtu.be/${ID}?t=90`)?.embed).toBe(`${EMBED}?start=90`)
		expect(readVideo(`https://www.youtube.com/watch?v=${ID}&t=1m30s`)?.embed).toBe(
			`${EMBED}?start=90`,
		)
	})

	it('keeps the privacy-enhanced player for somebody who chose it', () => {
		expect(readVideo(`https://www.youtube-nocookie.com/embed/${ID}`)?.embed).toBe(
			`https://www.youtube-nocookie.com/embed/${ID}`,
		)
	})

	it('plays a playlist, from its page or its embed', () => {
		const list = 'PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG'
		const played = `https://www.youtube.com/embed/videoseries?list=${list}`

		expect(readVideo(`https://www.youtube.com/playlist?list=${list}`)?.embed).toBe(played)
		expect(readVideo(played)?.embed).toBe(played)
	})

	it('reads Vimeo, including the private part of an unlisted link', () => {
		const player = 'https://player.vimeo.com/video/76979871'

		expect(readVideo('https://vimeo.com/76979871')).toEqual({ service: 'vimeo', embed: player })
		expect(readVideo('https://vimeo.com/channels/staffpicks/76979871')?.embed).toBe(player)
		expect(readVideo('https://vimeo.com/76979871/8272ddf2d4')?.embed).toBe(
			`${player}?h=8272ddf2d4`,
		)
		expect(readVideo(`${player}?h=8272ddf2d4`)?.embed).toBe(`${player}?h=8272ddf2d4`)
	})

	it.each([
		'',
		'not a link',
		'javascript:alert(1)',
		// The right shape on the wrong host.
		`https://evil.example/watch?v=${ID}`,
		`https://www.youtube.com.evil.example/watch?v=${ID}`,
		// On YouTube, but not a video -- the old check would have framed these.
		'https://www.youtube.com/redirect?q=https://evil.example',
		'https://www.youtube.com/@somechannel',
		'https://www.youtube.com/embed/videoseries',
		// An id that is not one.
		'https://www.youtube.com/watch?v=<script>',
		'https://www.youtube.com/watch?v=abc123',
	])('refuses %j', (link) => {
		expect(readVideo(link)).toBeNull()
	})
})
