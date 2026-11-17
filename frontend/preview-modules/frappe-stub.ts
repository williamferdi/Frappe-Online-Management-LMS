// The network, for a preview of the module builder: the real lib/frappe with
// its two calls answered from a course held in memory. Saves are applied to
// that course, so an edit shows the way it would after the server answered.
import type { OutlineItem, OutlineModule, StaffOutline } from '@/types'

export * from '../src/lib/frappe'

function item(over: Partial<OutlineItem>): OutlineItem {
	return {
		name: 'CMI-0',
		module: 'CM-1',
		item_type: 'Lesson',
		title: 'Lecture',
		position: 0,
		indent: 0,
		published: 1,
		lesson: null,
		assignment: null,
		page: null,
		file: null,
		url: null,
		completion_requirement: 'Nothing',
		min_score: null,
		progress: null,
		complete: false,
		locked: false,
		lock_reason: null,
		...over,
	}
}

function unit(over: Partial<OutlineModule>): OutlineModule {
	return {
		name: 'CM-1',
		title: 'Week 1',
		position: 0,
		published: 1,
		unlock_at: null,
		require_sequential_progress: 0,
		prerequisites: [],
		state: { open: true, reason: null },
		complete: false,
		items: [],
		...over,
	}
}

const outline: StaffOutline = {
	modules: [
		unit({
			name: 'CM-1',
			title: 'Week 1 — Creation',
			items: [
				item({ name: 'CMI-1', item_type: 'Sub-header', title: 'Course Materials' }),
				item({
					name: 'CMI-2',
					position: 1,
					title: 'Lecture 1: In the beginning',
					lesson: 'LES-1',
					completion_requirement: 'View it',
				}),
				item({
					name: 'CMI-3',
					position: 2,
					item_type: 'Page',
					title: 'Syllabus',
					page: 'CP-1',
					indent: 1,
				}),
				item({
					name: 'CMI-4',
					position: 3,
					item_type: 'Assignment',
					title: 'Reflection paper',
					assignment: 'CA-1',
					completion_requirement: 'Score at least',
					min_score: 70,
				}),
				item({
					name: 'CMI-5',
					position: 4,
					item_type: 'URL',
					title: 'Genesis 1 on Bible.com',
					url: 'https://www.bible.com/bible/1/GEN.1',
				}),
			],
		}),
		unit({
			name: 'CM-2',
			title: 'Week 2 — The Fall',
			position: 1,
			published: 0,
			items: [
				item({
					name: 'CMI-6',
					module: 'CM-2',
					item_type: 'File',
					title: 'Reading pack',
					file: 'CF-1',
				}),
			],
		}),
	],
	choices: {
		lessons: [{ name: 'LES-1', title: 'Lecture 1: In the beginning', chapter: 'CH-1' }],
		assignments: [{ name: 'CA-1', title: 'Reflection paper' }],
		pages: [{ name: 'CP-1', title: 'Syllabus', published: 1 }],
		files: [{ name: 'CF-1', title: 'Reading pack' }],
		item_types: ['Lesson', 'Assignment', 'Page', 'File', 'URL', 'Sub-header'],
		completion_rules: ['Nothing', 'View it', 'Mark it done', 'Score at least'],
	},
}

const posts: { path: string; args: Record<string, unknown> }[] = []
;(window as unknown as { __posts: typeof posts }).__posts = posts

const pause = () => new Promise((resolve) => setTimeout(resolve, 150))

export async function frappeGet<T>(path: string): Promise<T> {
	await pause()
	if (path.includes('content_space')) {
		return { course: 'GEST501', lms_course: 'c', lessons: 1, authoring_url: null } as T
	}
	return structuredClone(outline) as T
}

export async function frappePost<T>(path: string, args: Record<string, unknown> = {}): Promise<T> {
	await pause()
	posts.push({ path, args })
	if (path.endsWith('.save_item') && typeof args.item === 'string') {
		for (const row of outline.modules) {
			const found = row.items.find((candidate) => candidate.name === args.item)
			if (found) Object.assign(found, args.values)
		}
	}
	return {} as T
}
