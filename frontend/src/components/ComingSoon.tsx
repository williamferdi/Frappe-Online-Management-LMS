import { Hammer } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'

/**
 * An honest placeholder. The navigation shows the finished shape of the
 * product from the first release, so a screen that is not built yet says which
 * phase it arrives in rather than pretending to be empty.
 */
export function ComingSoon({
	title,
	phase,
	description,
}: {
	title: string
	phase: string
	description: string
}) {
	return (
		<>
			<PageHeader title={title} />
			<Card>
				<CardContent className="flex flex-col items-center gap-3 py-14 text-center">
					<div className="bg-accent text-accent-foreground grid size-11 place-items-center rounded-full">
						<Hammer className="size-5" />
					</div>
					<div className="text-base font-medium">Not built yet</div>
					<p className="text-muted-foreground max-w-md text-sm">{description}</p>
					<div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
						Arrives in {phase}
					</div>
				</CardContent>
			</Card>
		</>
	)
}
