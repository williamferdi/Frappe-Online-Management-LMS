import { describe, expect, it } from 'vitest'

import type { Boot } from './frappe'
import { isGuest, isStaff, isStudent, landingRoute } from './session'

const session = (roles: string[], user = 'a@example.com'): Boot => ({
	csrf_token: 'x',
	user,
	full_name: 'A',
	user_image: null,
	roles,
	student: null,
	enrollment: null,
	site_name: 'test.local',
	app_version: '',
})

describe('roles decide where someone lands', () => {
	it('sends a guest to the sign-in page', () => {
		expect(landingRoute(session(['Guest'], 'Guest'))).toBe('/portal/login')
		expect(isGuest(session(['Guest'], 'Guest'))).toBe(true)
	})

	it('sends a student to the portal', () => {
		expect(landingRoute(session(['Student', 'LMS Student']))).toBe('/portal')
	})

	it.each([
		'Registrar',
		'Admissions Officer',
		'Academic Coordinator',
		'Dean',
		'Accounts',
		'Faculty',
		'Facilitator',
		'Formation Coordinator',
		'System Manager',
	])('sends %s to the console', (role) => {
		expect(landingRoute(session([role]))).toBe('/staff')
	})

	it('prefers the console for staff who are also enrolled', () => {
		// A Registrar taking a course still wants the console when they type
		// the bare address.
		const both = session(['Registrar', 'Student'])
		expect(isStaff(both)).toBe(true)
		expect(isStudent(both)).toBe(true)
		expect(landingRoute(both)).toBe('/staff')
	})

	it('does not treat LMS Student as staff', () => {
		expect(isStaff(session(['LMS Student']))).toBe(false)
	})
})
