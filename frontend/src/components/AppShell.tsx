import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Menu, X, type LucideIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { UserMenu } from '@/components/UserMenu'
import { ThemeToggle } from '@/components/ThemeToggle'
import { cn } from '@/lib/utils'

export interface NavItem {
	to: string
	label: string
	icon: LucideIcon
	end?: boolean
	badge?: string
}

export interface NavSection {
	heading?: string
	items: NavItem[]
}

interface AppShellProps {
	product: string
	sections: NavSection[]
}

export function AppShell({ product, sections }: AppShellProps) {
	const [open, setOpen] = useState(false)
	const location = useLocation()

	// A tap on a nav link should close the drawer; without this the new page
	// renders behind the menu on a phone.
	useEffect(() => setOpen(false), [location.pathname])

	return (
		<div className="bg-background min-h-svh">
			<a
				href="#main"
				className="bg-primary text-primary-foreground sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:px-4 focus:py-2"
			>
				Skip to content
			</a>

			{open && (
				<button
					aria-label="Close navigation"
					className="fixed inset-0 z-30 bg-foreground/25 backdrop-blur-[2px] lg:hidden"
					onClick={() => setOpen(false)}
				/>
			)}

			<aside
				className={cn(
					'bg-sidebar border-sidebar-border fixed inset-y-0 left-0 z-40 flex w-[15.5rem] flex-col border-r transition-transform duration-200 lg:translate-x-0',
					open ? 'translate-x-0' : '-translate-x-full',
				)}
			>
				<div className="flex h-14 items-center gap-2.5 px-4">
					<Brand />
					<div className="min-w-0">
						<div className="truncate text-sm font-semibold leading-tight">SIBBCS</div>
						<div className="text-muted-foreground truncate text-[11px] leading-tight">
							{product}
						</div>
					</div>
					<Button
						variant="ghost"
						size="icon"
						className="ml-auto lg:hidden"
						onClick={() => setOpen(false)}
						aria-label="Close navigation"
					>
						<X />
					</Button>
				</div>

				<nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4">
					{sections.map((section, index) => (
						<div key={section.heading ?? index} className="space-y-0.5">
							{section.heading && (
								<div className="text-muted-foreground px-2.5 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider">
									{section.heading}
								</div>
							)}
							{section.items.map((item) => (
								<NavLink
									key={item.to}
									to={item.to}
									end={item.end}
									className={({ isActive }) =>
										cn(
											'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors',
											isActive
												? 'bg-primary/10 text-primary'
												: 'text-sidebar-foreground hover:bg-muted',
										)
									}
								>
									<item.icon className="size-4 shrink-0" />
									<span className="truncate">{item.label}</span>
									{item.badge && (
										<span className="bg-primary text-primary-foreground ml-auto rounded-full px-1.5 py-0.5 text-[10px] font-semibold">
											{item.badge}
										</span>
									)}
								</NavLink>
							))}
						</div>
					))}
				</nav>
			</aside>

			<div className="lg:pl-[15.5rem]">
				<header className="bg-background/85 border-border sticky top-0 z-20 flex h-14 items-center gap-2 border-b px-4 backdrop-blur-md sm:px-6">
					<Button
						variant="ghost"
						size="icon"
						className="lg:hidden"
						onClick={() => setOpen(true)}
						aria-label="Open navigation"
					>
						<Menu />
					</Button>
					<div className="ml-auto flex items-center gap-1">
						<ThemeToggle />
						<UserMenu />
					</div>
				</header>

				<main id="main" className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
					<Outlet />
				</main>
			</div>
		</div>
	)
}

function Brand() {
	return (
		<div
			aria-hidden
			className="bg-primary text-primary-foreground grid size-9 shrink-0 place-items-center rounded-lg font-serif text-base font-semibold"
		>
			S
		</div>
	)
}
