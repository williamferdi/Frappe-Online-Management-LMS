import { useQuery } from '@tanstack/react-query'
import { ChartPie } from 'lucide-react'

import { Donut, type DonutKind } from '@/components/Donut'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { frappeGet } from '@/lib/frappe'
import type { Demographics as Data } from '@/types'

/**
 * The roll at a glance.
 *
 * Deliberately the whole roll rather than whatever the list below is filtered
 * to: these panels are a standing description of the college, and a search box
 * that made them jump would make them useless for the thing they are for.
 */
export function Demographics() {
	const query = useQuery({
		queryKey: ['academic', 'demographics'],
		queryFn: () => frappeGet<Data>('sibbcs.api.academic_api.demographics'),
	})

	if (query.isPending) {
		return (
			<Card className="mb-4">
				<CardContent className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
					{Array.from({ length: 6 }, (_, index) => (
						<Skeleton key={index} className="h-64" />
					))}
				</CardContent>
			</Card>
		)
	}

	// A panel nobody can read is not worth an error: the list below is the page.
	if (query.error || !query.data || query.data.total === 0) return null

	const data = query.data

	return (
		<Card className="mb-4 overflow-hidden py-0">
			<div className="bg-primary text-primary-foreground flex items-center gap-3 px-5 py-3">
				<ChartPie className="size-5 shrink-0" />
				<div>
					<h2 className="text-base font-semibold leading-tight">
						Enrolled student demographics
					</h2>
					<p className="text-primary-foreground/75 text-[11px] font-medium uppercase tracking-wider">
						{data.total} students on the roll
					</p>
				</div>
			</div>

			<CardContent className="grid gap-x-6 gap-y-8 p-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
				{data.panels.map((panel) => (
					<Donut
						key={panel.key}
						title={panel.title}
						slices={panel.slices}
						kind={panel.kind as DonutKind}
						total={data.total}
					/>
				))}
			</CardContent>
		</Card>
	)
}
