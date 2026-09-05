import { createContext, useContext, useId, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

/**
 * A minimal tab control.
 *
 * Deliberately hand-written rather than `@radix-ui/react-tabs`: the bundle is
 * committed to git, so every dependency is a permanent addition to what the
 * portal ships, and what this needs -- roving focus, the right roles, and
 * arrow keys -- is about sixty lines. If tabs ever grow orientation,
 * animation or lazy panels, swap in Radix and delete this.
 */

type TabsContext = {
	value: string
	setValue: (value: string) => void
	baseId: string
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
	className,
	children,
}: {
	defaultValue: string
	value?: string
	onValueChange?: (value: string) => void
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
		<Ctx.Provider value={{ value, setValue, baseId }}>
			<div className={className}>{children}</div>
		</Ctx.Provider>
	)
}

export function TabsList({
	className,
	children,
}: {
	className?: string
	children: React.ReactNode
}) {
	const list = useRef<HTMLDivElement>(null)

	/** Left and right move between tabs, which is what a tablist owes a keyboard. */
	const onKeyDown = (event: React.KeyboardEvent) => {
		const keys = ['ArrowRight', 'ArrowLeft', 'Home', 'End']
		if (!keys.includes(event.key)) return

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
					: (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
		tabs[next]?.focus()
		tabs[next]?.click()
	}

	return (
		<div
			ref={list}
			role="tablist"
			onKeyDown={onKeyDown}
			className={cn(
				'bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-lg p-1',
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
	const { value: active, setValue, baseId } = useTabs('TabsTrigger')
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
				'ring-offset-background focus-visible:ring-ring inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none',
				selected
					? 'bg-background text-foreground shadow-sm'
					: 'hover:text-foreground cursor-pointer',
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
	const { value: active, baseId } = useTabs('TabsContent')
	if (active !== value) return null

	return (
		<div
			role="tabpanel"
			id={`${baseId}-panel-${value}`}
			aria-labelledby={`${baseId}-tab-${value}`}
			tabIndex={0}
			className={cn('mt-4 focus-visible:outline-none', className)}
		>
			{children}
		</div>
	)
}
