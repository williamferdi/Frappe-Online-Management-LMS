import { createBrowserRouter, Navigate, useParams } from 'react-router-dom'

import { boot } from '@/lib/frappe'
import { landingRoute } from '@/lib/session'
import { Login } from '@/routes/Login'
import { RequireAuth } from '@/routes/RequireAuth'
import { Admissions } from '@/routes/staff/Admissions'
import { ApplicationDetail } from '@/routes/staff/ApplicationDetail'
import { Academic } from '@/routes/staff/Academic'
import { CourseDetail } from '@/routes/staff/CourseDetail'
import { Courses } from '@/routes/staff/Courses'
import { MarkingQueue } from '@/routes/staff/MarkingQueue'
import { Finance } from '@/routes/staff/Finance'
import { GradeSheet } from '@/routes/staff/GradeSheet'
import { RecordDetail } from '@/routes/staff/RecordDetail'
import { RecordIndex } from '@/routes/staff/RecordIndex'
import { RecordList } from '@/routes/staff/RecordList'
import { Reports } from '@/routes/staff/Reports'
import { StaffDashboard } from '@/routes/staff/StaffDashboard'
import { StudentDetail } from '@/routes/staff/StudentDetail'
import { Students } from '@/routes/staff/Students'
import { Users } from '@/routes/staff/Users'
import { StaffLayout } from '@/routes/staff/StaffLayout'
import { Dashboard } from '@/routes/portal/Dashboard'
import { Assignment } from '@/routes/portal/Assignment'
import { Coursework } from '@/routes/portal/Coursework'
import { CoursePlayer } from '@/routes/portal/CoursePlayer'
import { MyCourse } from '@/routes/portal/MyCourse'
import { QuizPlayer } from '@/routes/portal/QuizPlayer'
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

function MovedStudent() {
	const { name = '' } = useParams()
	return <Navigate to={`/staff/students/${encodeURIComponent(name)}`} replace />
}

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
					{ path: 'courses/:name/work', element: <Coursework /> },
					{ path: 'courses/:name/work/:assignment', element: <Assignment /> },
					{ path: 'courses/:name/modules', element: <MyCourse /> },
					{ path: 'courses/:name/learn', element: <CoursePlayer /> },
					{ path: 'courses/:name/learn/:item', element: <CoursePlayer /> },
					{
						path: 'courses/:name/quiz/:assignment',
						element: <QuizPlayer />,
					},
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
					{ path: 'courses', element: <Courses /> },
					{ path: 'courses/:name', element: <CourseDetail /> },
					{
						path: 'courses/:name/grade/:assignment',
						element: <MarkingQueue />,
					},
					{ path: 'students', element: <Students /> },
					{ path: 'students/:name', element: <StudentDetail /> },
					// The roll used to be a tab inside Academic. Anything already
					// linked or bookmarked there still lands on the profile.
					{ path: 'academic/students/:name', element: <MovedStudent /> },
					{ path: 'academic/offerings/:name', element: <GradeSheet /> },
					{ path: 'finance', element: <Finance /> },
					{ path: 'users', element: <Users /> },
					{ path: 'data', element: <RecordIndex /> },
					{ path: 'reports', element: <Reports /> },
					{ path: 'data/:doctype', element: <RecordList /> },
					{ path: 'data/:doctype/:name', element: <RecordDetail /> },
				],
			},
		],
	},

	{ path: '*', element: <Navigate to={landingRoute(boot)} replace /> },
])
