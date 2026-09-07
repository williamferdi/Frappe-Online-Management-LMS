import { createContext, useContext, useId, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

/**
 * A minimal tab control.
 *
 * Deliberately hand-written rather than `@radix-ui/react-tabs`: the bundle is
 * committed to git, so every dependency is a permanent addition to what the
 * portal ships, and what this needs -- roving focus, the right roles, and
 * arrow keys -- is about sixty lines.
 *
 * This used to say "if tabs ever grow orientation, swap in Radix and delete
 * this". Orientation arrived with the course workspace and cost about ten
 * lines, so the tripwire was in the wrong place rather than the decision. What
 * would still justify the swap is animation or lazily-mounted panels, neither
 * of which is worth hand-writing.
 */

type Orientation = 'horizontal' | 'vertical'

type TabsContext = {
	value: string
	setValue: (value: string) => void
	baseId: string
	orientation: Orientation
}

const Ctx = createContext<TabsContext | null>(null)

function useTabs(component: string) {
	const context = useContext(Ctx)
	if (!context) throw new Error(`<${component}> must be used inside <Tabs>`)
	return context
}

export function Tabs({
	defaultValue,
	value: controlled,
	onValueChange,
	orientation = 'horizontal',
	className,
	children,
}: {
	defaultValue: string
	value?: string
	onValueChange?: (value: string) => void
	orientation?: Orientation
	className?: string
	children: React.ReactNode
}) {
	const [uncontrolled, setUncontrolled] = useState(defaultValue)
	const baseId = useId()
	const value = controlled ?? uncontrolled

	const setValue = (next: string) => {
		if (controlled === undefined) setUncontrolled(next)
		onValueChange?.(next)
	}

	return (
		<Ctx.Provider value={{ value, setValue, baseId, orientation }}>
			<div className={className}>{children}</div>
		</Ctx.Provider>
	)
}

export function TabsList({
	className,
	label,
	children,
}: {
	className?: string
	/** Names the set for a screen reader, which matters more when the list is
	 *  a course's navigation than when it is two tabs over one card. */
	label?: string
	children: React.ReactNode
}) {
	const { orientation } = useTabs('TabsList')
	const list = useRef<HTMLDivElement>(null)

	/** The arrows that move between tabs are the ones that point along the
	 *  list: left and right across a strip, up and down beside a panel. */
	const onKeyDown = (event: React.KeyboardEvent) => {
		const [back, forward] =
			orientation === 'vertical'
				? ['ArrowUp', 'ArrowDown']
				: ['ArrowLeft', 'ArrowRight']
		if (![back, forward, 'Home', 'End'].includes(event.key)) return

		const tabs = Array.from(
			list.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? [],
		)
		const current = tabs.findIndex((tab) => tab === document.activeElement)
		if (current < 0) return

		event.preventDefault()
		const next =
			event.key === 'Home'
				? 0
				: event.key === 'End'
					? tabs.length - 1
					: (current + (event.key === forward ? 1 : -1) + tabs.length) % tabs.length
		tabs[next]?.focus()
		tabs[next]?.click()
	}

	return (
		<div
			ref={list}
			role="tablist"
			aria-label={label}
			aria-orientation={orientation}
			onKeyDown={onKeyDown}
			className={cn(
				orientation === 'vertical'
					? // A course nav below `lg` has nowhere to be a column, so it
						// lies down and scrolls rather than eating the screen.
						'flex gap-0.5 overflow-x-auto pb-1 lg:flex-col lg:overflow-x-visible lg:pb-0'
					: // Wraps rather than running off the edge: a tab a narrow window
						// cuts off is a tab nobody can find.
						'bg-muted text-muted-foreground flex flex-wrap items-center gap-1 rounded-lg p-1',
				className,
			)}
		>
			{children}
		</div>
	)
}

export function TabsTrigger({
	value,
	className,
	children,
}: {
	value: string
	className?: string
	children: React.ReactNode
}) {
	const { value: active, setValue, baseId, orientation } = useTabs('TabsTrigger')
	const selected = active === value

	return (
		<button
			type="button"
			role="tab"
			id={`${baseId}-tab-${value}`}
			aria-selected={selected}
			aria-controls={`${baseId}-panel-${value}`}
			tabIndex={selected ? 0 : -1}
			onClick={() => setValue(value)}
			className={cn(
				'ring-offset-background focus-visible:ring-ring inline-flex items-center gap-2 text-sm font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none',
				orientation === 'vertical'
					? cn(
							// The rule marks the current page down the side of a column
							// and along the bottom of a strip -- the edge the list runs
							// against in each case.
							'shrink-0 justify-start rounded-md border-b-2 px-3 py-2 lg:w-full lg:border-b-0 lg:border-l-2',
							selected
								? 'bg-accent text-accent-foreground border-primary'
								: 'text-muted-foreground hover:text-foreground hover:bg-muted/60 cursor-pointer border-transparent',
						)
					: cn(
							'justify-center rounded-md px-3 py-1.5',
							selected
								? 'bg-background text-foreground shadow-sm'
								: 'hover:text-foreground cursor-pointer',
						),
				className,
			)}
		>
			{children}
		</button>
	)
}

export function TabsContent({
	value,
	className,
	children,
}: {
	value: string
	className?: string
	children: React.ReactNode
}) {
	const { value: active, baseId, orientation } = useTabs('TabsContent')
	if (active !== value) return null

	return (
		<div
			role="tabpanel"
			id={`${baseId}-panel-${value}`}
			aria-labelledby={`${baseId}-tab-${value}`}
			tabIndex={0}
			className={cn(
				// Beside a column the panel is already separated by the gap; the
				// gap under a strip is this margin.
				orientation === 'vertical' ? 'focus-visible:outline-none' : 'mt-4 focus-visible:outline-none',
				className,
			)}
		>
			{children}
		</div>
	)
}
