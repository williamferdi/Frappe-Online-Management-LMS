import type { LucideIcon } from 'lucide-react'

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

/**
 * The frame a course is worked on inside.
 *
 * Canvas puts a course's sections down the left of the course rather than
 * across the top, and that is the shape this borrows. It is not decoration:
 * seven sections in a horizontal strip wrap onto two lines and stop reading as
 * an order, while a column has room for the labels and somewhere to put a
 * count beside them.
 *
 * The section still lives in `?tab=`, exactly as it did as a strip, so every
 * link that already points into a course -- "No assignments set yet, *set
 * one*" -- keeps landing where it did.
 */

export interface CourseSection {
	value: string
	label: string
	icon: LucideIcon
	/** Shown beside the label when there is something to count. */
	count?: number
}

export function CourseWorkspace({
	sections,
	value,
	onValueChange,
	children,
}: {
	sections: CourseSection[]
	value: string
	onValueChange: (value: string) => void
	children: React.ReactNode
}) {
	return (
		<Tabs
			orientation="vertical"
			defaultValue={sections[0]?.value ?? ''}
			value={value}
			onValueChange={onValueChange}
			className="mt-4 flex flex-col gap-4 lg:flex-row lg:gap-6"
		>
			<TabsList label="Course sections" className="lg:w-52 lg:shrink-0">
				{sections.map((section) => {
					const Icon = section.icon
					return (
						<TabsTrigger key={section.value} value={section.value}>
							<Icon className="size-4 shrink-0" aria-hidden />
							<span className="truncate">{section.label}</span>
							{section.count ? (
								<span className="text-muted-foreground ml-auto hidden text-xs tabular-nums lg:inline">
									{section.count}
								</span>
							) : null}
						</TabsTrigger>
					)
				})}
			</TabsList>

			{/* `min-w-0` or a wide table inside a panel stretches the whole row
			    and pushes the nav off the screen. */}
			<div className="min-w-0 flex-1">{children}</div>
		</Tabs>
	)
}
