/**
 * A video link, read down to something the page may play.
 *
 * A teacher copies a link from wherever they found the video -- the address
 * bar gives `youtube.com/watch?v=…`, the Share button gives `youtu.be/…`, a
 * phone gives a Shorts link. Only YouTube's `/embed/` address may be put in a
 * frame: the watch page answers one with `X-Frame-Options: SAMEORIGIN`, which
 * the browser draws as "www.youtube.com refused to connect".
 *
 * So every form is read down to the video's id, and the address played is
 * built from that id alone. Nothing from the pasted link reaches an iframe's
 * `src` except an id checked character by character -- which is also what
 * keeps a lookalike host, or a redirect that happens to live on youtube.com,
 * out of the page.
 */

export interface Video {
	service: 'youtube' | 'vimeo'
	/** The address to frame. Built, never copied. */
	embed: string
}

const YOUTUBE_HOSTS = new Set([
	'youtube.com',
	'www.youtube.com',
	'm.youtube.com',
	'music.youtube.com',
	'youtube-nocookie.com',
	'www.youtube-nocookie.com',
])
const VIMEO_HOSTS = new Set(['vimeo.com', 'www.vimeo.com', 'player.vimeo.com'])

/** Every YouTube video id is eleven of these. */
const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/
const YOUTUBE_LIST = /^[A-Za-z0-9_-]{10,64}$/
const VIMEO_ID = /^\d{1,12}$/
/** The private part of an unlisted Vimeo link. */
const VIMEO_HASH = /^[0-9a-f]{6,20}$/

export function readVideo(input: string): Video | null {
	let url: URL
	try {
		url = new URL(input.trim())
	} catch {
		return null
	}
	if (url.protocol !== 'https:' && url.protocol !== 'http:') return null

	const host = url.hostname.toLowerCase()
	const parts = url.pathname.split('/').filter(Boolean)

	if (host === 'youtu.be' || YOUTUBE_HOSTS.has(host)) return youtube(url, host, parts)
	if (VIMEO_HOSTS.has(host)) return vimeo(url, host, parts)
	return null
}

function youtube(url: URL, host: string, parts: string[]): Video | null {
	const [first = '', second = ''] = parts
	// Somebody who chose the privacy-enhanced player keeps it.
	const base = host.endsWith('youtube-nocookie.com')
		? 'https://www.youtube-nocookie.com/embed/'
		: 'https://www.youtube.com/embed/'

	// A playlist, shared as its own page or as its own embed.
	const list = url.searchParams.get('list')
	if (
		(first === 'playlist' || (first === 'embed' && second === 'videoseries')) &&
		list &&
		YOUTUBE_LIST.test(list)
	) {
		return { service: 'youtube', embed: `${base}videoseries?list=${list}` }
	}

	let id: string | null = null
	if (host === 'youtu.be') id = first
	else if (first === 'watch') id = url.searchParams.get('v')
	else if (['embed', 'shorts', 'live', 'v'].includes(first)) id = second

	// `videoseries` is eleven characters too, and is not a video.
	if (!id || id === 'videoseries' || !YOUTUBE_ID.test(id)) return null

	// A link shared "from 1:30" should still start at 1:30.
	const start = seconds(url.searchParams.get('t') ?? url.searchParams.get('start'))
	return { service: 'youtube', embed: base + id + (start ? `?start=${start}` : '') }
}

function vimeo(url: URL, host: string, parts: string[]): Video | null {
	let id: string | undefined
	let hash = url.searchParams.get('h') ?? ''

	if (host === 'player.vimeo.com') {
		if (parts[0] === 'video') id = parts[1]
	} else {
		// `vimeo.com/123`, `vimeo.com/123/abc` for an unlisted video, or
		// `vimeo.com/channels/name/123` -- the id is the first run of digits.
		const at = parts.findIndex((part) => VIMEO_ID.test(part))
		if (at >= 0) {
			id = parts[at]
			if (!hash) hash = parts[at + 1] ?? ''
		}
	}

	if (!id || !VIMEO_ID.test(id)) return null
	return {
		service: 'vimeo',
		embed: `https://player.vimeo.com/video/${id}` + (VIMEO_HASH.test(hash) ? `?h=${hash}` : ''),
	}
}

/** `90`, `90s`, `1m30s`, `1h2m3s` -- the forms YouTube's share button writes. */
function seconds(value: string | null): number {
	if (!value) return 0
	if (/^\d+$/.test(value)) return Number(value)
	const match = /^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/.exec(value)
	if (!match) return 0
	return Number(match[1] ?? 0) * 3600 + Number(match[2] ?? 0) * 60 + Number(match[3] ?? 0)
}
