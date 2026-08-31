import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { boot } from '@/lib/frappe'
import { isGuest, isStaff } from '@/lib/session'

/**
 * Keeps signed-out visitors off the app routes and students out of the
 * console's navigation.
 *
 * This is not a security boundary and is not written as one -- every endpoint
 * checks permissions server-side. All this does is avoid rendering a shell full
 * of links that would fail.
 */
export function RequireAuth({ staffOnly = false }: { staffOnly?: boolean }) {
	const location = useLocation()

	if (isGuest(boot)) {
		return <Navigate to="/portal/login" replace state={{ from: location.pathname }} />
	}

	if (staffOnly && !isStaff(boot)) {
		return <Navigate to="/portal" replace />
	}

	return <Outlet />
}
