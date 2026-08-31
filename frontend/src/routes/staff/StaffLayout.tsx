import {
	BadgeIndianRupee,
	Database,
	GraduationCap,
	LayoutDashboard,
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
			{ to: '/staff/academic', label: 'Academic', icon: GraduationCap },
			{ to: '/staff/finance', label: 'Finance', icon: BadgeIndianRupee },
			{ to: '/staff/users', label: 'Users', icon: Users },
			{ to: '/staff/data', label: 'Records', icon: Database },
		],
	},
]

export function StaffLayout() {
	return <AppShell product="Staff Console" sections={SECTIONS} />
}
