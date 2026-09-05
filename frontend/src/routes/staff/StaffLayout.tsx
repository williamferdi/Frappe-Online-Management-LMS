import {
	BadgeIndianRupee,
	BarChart3,
	BookOpen,
	Database,
	GraduationCap,
	LayoutDashboard,
	UserCog,
	UserRoundCheck,
	Users,
} from 'lucide-react'

import { AppShell, type NavSection } from '@/components/AppShell'

const SECTIONS: NavSection[] = [
	{
		items: [{ to: '/staff', label: 'Overview', icon: LayoutDashboard, end: true }],
	},
	{
		heading: 'Operations',
		items: [
			{ to: '/staff/admissions', label: 'Admissions', icon: UserRoundCheck },
			{ to: '/staff/students', label: 'Students', icon: Users },
			{ to: '/staff/academic', label: 'Academic', icon: GraduationCap },
			{ to: '/staff/courses', label: 'Courses', icon: BookOpen },
			{ to: '/staff/finance', label: 'Finance', icon: BadgeIndianRupee },
			{ to: '/staff/users', label: 'Users', icon: UserCog },
			{ to: '/staff/data', label: 'Records', icon: Database },
			{ to: '/staff/reports', label: 'Reports', icon: BarChart3 },
		],
	},
]

export function StaffLayout() {
	return <AppShell product="Staff Console" sections={SECTIONS} />
}
