import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ComingSoon } from '@/components/ComingSoon'
import { boot } from '@/lib/frappe'
import { landingRoute } from '@/lib/session'
import { Login } from '@/routes/Login'
import { RequireAuth } from '@/routes/RequireAuth'
import { StaffLayout } from '@/routes/staff/StaffLayout'
import { MyCourses } from '@/routes/portal/MyCourses'
import { PortalLayout } from '@/routes/portal/PortalLayout'

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
					{
						index: true,
						...soon(
							'Dashboard',
							'Phase 1',
							'A single view of what needs your attention: courses in progress, what is due, and anything outstanding.',
						),
					},
					{ path: 'courses', element: <MyCourses /> },
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
							'grades',
							'Grades',
							'Phase 1',
							'Your marks for each course, the components behind them, and your CGPA over time.',
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
						[
							'profile',
							'Profile',
							'Phase 1',
							'Your contact details, photograph and password.',
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
