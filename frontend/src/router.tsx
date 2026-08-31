import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ComingSoon } from '@/components/ComingSoon'
import { boot } from '@/lib/frappe'
import { landingRoute } from '@/lib/session'
import { Login } from '@/routes/Login'
import { RequireAuth } from '@/routes/RequireAuth'
import { Admissions } from '@/routes/staff/Admissions'
import { ApplicationDetail } from '@/routes/staff/ApplicationDetail'
import { Academic } from '@/routes/staff/Academic'
import { GradeSheet } from '@/routes/staff/GradeSheet'
import { StaffDashboard } from '@/routes/staff/StaffDashboard'
import { StudentDetail } from '@/routes/staff/StudentDetail'
import { StaffLayout } from '@/routes/staff/StaffLayout'
import { Dashboard } from '@/routes/portal/Dashboard'
import { Grades } from '@/routes/portal/Grades'
import { MyCourses } from '@/routes/portal/MyCourses'
import { PortalLayout } from '@/routes/portal/PortalLayout'
import { Profile } from '@/routes/portal/Profile'
import { Announcements } from '@/routes/portal/Announcements'
import { Calendar } from '@/routes/portal/Calendar'
import { Discussions } from '@/routes/portal/Discussions'
import { Inbox } from '@/routes/portal/Inbox'
import { Register } from '@/routes/portal/Register'
import { ToDo } from '@/routes/portal/ToDo'

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
					{ path: 'todo', element: <ToDo /> },
					{ path: 'calendar', element: <Calendar /> },
					{ path: 'inbox', element: <Inbox /> },
					{ path: 'discussions', element: <Discussions /> },
					{ path: 'announcements', element: <Announcements /> },
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
					{ index: true, element: <StaffDashboard /> },
					{ path: 'admissions', element: <Admissions /> },
					{ path: 'admissions/:name', element: <ApplicationDetail /> },
					{ path: 'academic', element: <Academic /> },
					{ path: 'academic/students/:name', element: <StudentDetail /> },
					{ path: 'academic/offerings/:name', element: <GradeSheet /> },
					...[
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
