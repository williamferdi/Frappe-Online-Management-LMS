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
import { useUnreadCounts } from '@/hooks/useComms'

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
	const { data } = useUnreadCounts()

	// The counts are polled, so the badge can be a minute behind. Rebuilding
	// the section here rather than mutating SECTIONS keeps that constant a
	// constant -- a module-level array edited on render is shared by every
	// mount and outlives the component that changed it.
	const sections: NavSection[] = SECTIONS.map((section) => ({
		...section,
		items: section.items.map((item) => {
			const unread =
				item.to === '/portal/inbox'
					? data?.inbox
					: item.to === '/portal/announcements'
						? data?.announcements
						: 0
			return unread ? { ...item, badge: String(unread) } : item
		}),
	}))

	// A course wants the width: the player has its own module sidebar, and two
	// of them either side of a lesson leaves the reading squeezed in the middle.
	return (
		<AppShell
			product="Student Portal"
			sections={sections}
			collapseOn={(pathname) => pathname.startsWith('/portal/courses')}
		/>
	)
}
