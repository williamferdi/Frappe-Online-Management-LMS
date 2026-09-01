import type { LucideIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

/** A filter pill. Shared so the students page and the academic tabs agree. */
export function Chip({
	label,
	active,
	onClick,
}: {
	label: string
	active: boolean
	onClick: () => void
}) {
	return (
		<Button
			size="sm"
			variant={active ? 'default' : 'outline'}
			className="h-8"
			onClick={onClick}
		>
			{label}
		</Button>
	)
}

/** Nothing to show, and why -- an empty table with no explanation reads as a fault. */
export function Empty({
	icon: Icon,
	title,
	detail,
}: {
	icon: LucideIcon
	title: string
	detail: string
}) {
	return (
		<Card>
			<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
				<Icon className="text-muted-foreground size-6" />
				<div className="font-medium">{title}</div>
				<p className="text-muted-foreground max-w-sm text-sm">{detail}</p>
			</CardContent>
		</Card>
	)
}
