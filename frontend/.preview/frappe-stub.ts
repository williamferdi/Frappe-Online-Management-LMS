/**
 * The network, replaced by three payloads taken off the live site.
 *
 * Everything else about the screen is the real thing -- the real components,
 * the real stylesheet, the real tokens. Only the fetch is swapped, so the
 * picture this produces is the page as it is, not a drawing of it.
 */
export {
	FrappeError,
	boot,
	readBoot,
	frappeCall,
	frappeUpload,
	STUDENT_HOME,
	STAFF_HOME,
	login,
	logout,
} from '../src/lib/frappe'

import live from './payloads.json'
import shaped from './shaped.json'

/** `?demo` swaps the outline for one carrying a sub-header, an indent and a
 *  draft -- none of which the live course happens to use yet. */
const useShaped = window.location.search.includes('demo')

export const frappeGet = async <T,>(path: string): Promise<T> => {
	if (path.includes('content_space')) return live.space as T
	if (path.includes('syllabus.outline')) {
		return (useShaped ? shaped : live.outline) as T
	}
	return live.course as T
}

export const frappePost = async <T,>(): Promise<T> => ({}) as T
