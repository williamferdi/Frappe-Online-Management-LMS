import { boot, type Boot } from './frappe'

/**
 * Who gets the staff console. The list mirrors `sibbcs/setup/permissions.py`
 * plus Dean, which `level_promotion.APPROVER_ROLES` recognises but the
 * permission matrix does not name.
 *
 * This decides *navigation only*. Every endpoint checks permissions itself;
 * nothing here is a security boundary.
 */
export const STAFF_ROLES = [
	'System Manager',
	'Registrar',
	'Admissions Officer',
	'Academic Coordinator',
	'Dean',
	'Faculty',
	'Facilitator',
	'Formation Coordinator',
	'Accounts',
] as const

export function hasRole(session: Boot, ...roles: string[]): boolean {
	return roles.some((role) => session.roles.includes(role))
}

export function isStaff(session: Boot = boot): boolean {
	return hasRole(session, ...STAFF_ROLES)
}

export function isStudent(session: Boot = boot): boolean {
	return session.roles.includes('Student')
}

export function isGuest(session: Boot = boot): boolean {
	return session.user === 'Guest' || !session.user
}

/**
 * Where someone belongs when they arrive at the root.
 *
 * Staff first: a Registrar who is also enrolled somewhere still wants the
 * console when they type the bare address.
 */
export function landingRoute(session: Boot = boot): string {
	if (isGuest(session)) return '/portal/login'
	if (isStaff(session)) return '/staff'
	return '/portal'
}
