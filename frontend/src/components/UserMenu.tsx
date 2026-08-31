import { Link, useLocation } from 'react-router-dom'
import { GraduationCap, LayoutGrid, LogOut, ShieldCheck, User as UserIcon } from 'lucide-react'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { boot, logout, STAFF_HOME, STUDENT_HOME } from '@/lib/frappe'
import { isStaff, isStudent } from '@/lib/session'
import { initials } from '@/lib/utils'

export function UserMenu() {
	const { pathname } = useLocation()
	const inStaffConsole = pathname.startsWith(STAFF_HOME)

	// Administrator holds every role, and a Registrar may well be enrolled on a
	// course. Whoever belongs in both places needs a way across that is not
	// typing the address into the bar.
	const showConsoleLink = isStaff() && !inStaffConsole
	const showPortalLink = isStudent() && inStaffConsole

	return (
		<DropdownMenu>
			<DropdownMenuTrigger
				className="hover:bg-muted rounded-full p-0.5 transition-colors"
				aria-label="Account menu"
			>
				<Avatar>
					{boot.user_image && <AvatarImage src={boot.user_image} alt="" />}
					<AvatarFallback>{initials(boot.full_name)}</AvatarFallback>
				</Avatar>
			</DropdownMenuTrigger>

			<DropdownMenuContent align="end" className="min-w-56">
				<DropdownMenuLabel className="text-foreground text-sm font-medium">
					{boot.full_name}
					<div className="text-muted-foreground truncate text-xs font-normal">
						{boot.user}
					</div>
				</DropdownMenuLabel>
				<DropdownMenuSeparator />

				{(showConsoleLink || showPortalLink) && (
					<>
						{showConsoleLink && (
							<DropdownMenuItem asChild>
								<Link to={STAFF_HOME}>
									<ShieldCheck /> Staff console
								</Link>
							</DropdownMenuItem>
						)}
						{showPortalLink && (
							<DropdownMenuItem asChild>
								<Link to={STUDENT_HOME}>
									<GraduationCap /> Student portal
								</Link>
							</DropdownMenuItem>
						)}
						<DropdownMenuSeparator />
					</>
				)}

				<DropdownMenuItem asChild>
					<Link to="/portal/profile">
						<UserIcon /> Profile
					</Link>
				</DropdownMenuItem>

				{isStaff() && (
					<DropdownMenuItem asChild>
						<a href="/app">
							<LayoutGrid /> Frappe Desk
						</a>
					</DropdownMenuItem>
				)}

				<DropdownMenuSeparator />
				<DropdownMenuItem variant="destructive" onSelect={() => void logout()}>
					<LogOut /> Sign out
				</DropdownMenuItem>
			</DropdownMenuContent>
		</DropdownMenu>
	)
}
