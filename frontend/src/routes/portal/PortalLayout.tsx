import {
	BookOpen,
	CalendarDays,
	CircleUser,
	GraduationCap,
	Inbox,
	LayoutDashboard,
	ListTodo,
	Megaphone,
	MessagesSquare,
} from 'lucide-react'

import { AppShell, type NavSection } from '@/components/AppShell'

/** The shape the college asked for, in the order they asked for it. */
const SECTIONS: NavSection[] = [
	{
		items: [
			{ to: '/portal', label: 'Dashboard', icon: LayoutDashboard, end: true },
			{ to: '/portal/courses', label: 'My Courses', icon: BookOpen },
			{ to: '/portal/todo', label: 'To Do', icon: ListTodo },
			{ to: '/portal/calendar', label: 'Calendar', icon: CalendarDays },
			{ to: '/portal/inbox', label: 'Inbox', icon: Inbox },
			{ to: '/portal/grades', label: 'Grades', icon: GraduationCap },
			{ to: '/portal/discussions', label: 'Discussions', icon: MessagesSquare },
			{ to: '/portal/announcements', label: 'Announcements', icon: Megaphone },
			{ to: '/portal/profile', label: 'Profile', icon: CircleUser },
		],
	},
]

export function PortalLayout() {
	return <AppShell product="Student Portal" sections={SECTIONS} />
}
