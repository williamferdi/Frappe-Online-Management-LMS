import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ComingSoon } from '@/components/ComingSoon'
import { boot } from '@/lib/frappe'
import { landingRoute } from '@/lib/session'
import { Login } from '@/routes/Login'
import { RequireAuth } from '@/routes/RequireAuth'
import { StaffLayout } from '@/routes/staff/StaffLayout'
import { Dashboard } from '@/routes/portal/Dashboard'
import { Grades } from '@/routes/portal/Grades'
import { MyCourses } from '@/routes/portal/MyCourses'
import { PortalLayout } from '@/routes/portal/PortalLayout'
import { Profile } from '@/routes/portal/Profile'
import { Register } from '@/routes/portal/Register'

const soon = (title: string, phase: string, description: string) => ({
	element: <ComingSoon title={title} phase={phase} description={description} />,
})

export const router = createBrowserRouter([
	{ path: '/', element: <Navigate to={landingRoute(boot)} replace /> },

	{ path: '/portal/login', element: <Login /> },

	{
		element: <RequireAuth />,
		children: [
			{
				path: '/portal',
				element: <PortalLayout />,
				children: [
					{ index: true, element: <Dashboard /> },
					{ path: 'courses', element: <MyCourses /> },
					// Registration hangs off My Courses rather than taking a tenth
					// slot in a navigation the college specified as nine.
					{ path: 'courses/register', element: <Register /> },
					{ path: 'grades', element: <Grades /> },
					{ path: 'profile', element: <Profile /> },
					...[
						[
							'todo',
							'To Do',
							'Phase 2',
							'Assignments due, fees outstanding and forms awaiting your signature, gathered from across the system.',
						],
						[
							'calendar',
							'Calendar',
							'Phase 2',
							'Live sessions, assignment deadlines, fee due dates and term boundaries on one calendar.',
						],
						[
							'inbox',
							'Inbox',
							'Phase 2',
							'Messages from the Registrar, your instructors and the Student Services office.',
						],
						[
							'discussions',
							'Discussions',
							'Phase 2',
							'Course discussion threads with your cohort and instructors.',
						],
						[
							'announcements',
							'Announcements',
							'Phase 2',
							'Notices from the college, filtered to your programme, level and courses.',
						],
					].map(([path, title, phase, description]) => ({
						path,
						...soon(title, phase, description),
					})),
				],
			},
		],
	},

	{
		element: <RequireAuth staffOnly />,
		children: [
			{
				path: '/staff',
				element: <StaffLayout />,
				children: [
					{
						index: true,
						...soon(
							'Overview',
							'Phase 3',
							'The admissions funnel, enrolment by level, fee collection and LMS activity at a glance.',
						),
					},
					...[
						[
							'admissions',
							'Admissions',
							'Phase 3',
							'The application pipeline as a board and a table, with the thirteen-step checklist and every action on one screen.',
						],
						[
							'academic',
							'Academic',
							'Phase 4',
							'Students, enrolments, offerings, registrations, level promotions and grade entry.',
						],
						[
							'finance',
							'Finance',
							'Phase 5',
							'Invoices, payments, collection and scholarship decisions.',
						],
						['users', 'Users', 'Phase 5', 'Accounts, roles and access.'],
					].map(([path, title, phase, description]) => ({
						path,
						...soon(title, phase, description),
					})),
				],
			},
		],
	},

	{ path: '*', element: <Navigate to={landingRoute(boot)} replace /> },
])
