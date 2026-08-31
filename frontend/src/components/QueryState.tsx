import type { UseQueryResult } from '@tanstack/react-query'
import { AlertCircle, GraduationCap } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { FrappeError } from '@/lib/frappe'

interface QueryStateProps<T> {
	query: UseQueryResult<T>
	title: string
	/** Signed in, but not enrolled yet -- an ordinary state, not an error. */
	emptyWhen?: (data: T) => boolean
	empty?: React.ReactNode
	children: (data: T) => React.ReactNode
}

/**
 * Loading, failure and not-enrolled-yet, in one place.
 *
 * Every screen in the portal has the same three preludes before it has
 * anything to draw, and writing them per screen is how one of them ends up
 * showing a blank page instead of a reason.
 */
export function QueryState<T>({
	query,
	title,
	emptyWhen,
	empty,
	children,
}: QueryStateProps<T>) {
	if (query.isPending) {
		return (
			<>
				<PageHeader title={title} />
				<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
					{Array.from({ length: 4 }, (_, i) => (
						<Skeleton key={i} className="h-[5.25rem]" />
					))}
				</div>
				<div className="mt-6 space-y-3">
					{Array.from({ length: 3 }, (_, i) => (
						<Skeleton key={i} className="h-24" />
					))}
				</div>
			</>
		)
	}

	if (query.error) {
		const message =
			query.error instanceof FrappeError
				? query.error.message
				: 'Something went wrong loading this page.'
		return (
			<>
				<PageHeader title={title} />
				<Card>
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<AlertCircle className="text-destructive size-6" />
						<div className="font-medium">Could not load {title.toLowerCase()}</div>
						<p className="text-muted-foreground max-w-sm text-sm">{message}</p>
						<Button
							variant="outline"
							size="sm"
							className="mt-1"
							onClick={() => void query.refetch()}
						>
							Try again
						</Button>
					</CardContent>
				</Card>
			</>
		)
	}

	const data = query.data as T
	if (emptyWhen?.(data)) {
		return (
			<>
				<PageHeader title={title} />
				{empty ?? <NoEnrollment />}
			</>
		)
	}

	return <>{children(data)}</>
}

export function NoEnrollment() {
	return (
		<Card>
			<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
				<GraduationCap className="text-muted-foreground size-6" />
				<div className="font-medium">No active enrollment</div>
				<p className="text-muted-foreground max-w-sm text-sm">
					Your account is not linked to an active programme enrolment yet. The
					Registrar's office will complete this once your admission is confirmed.
				</p>
			</CardContent>
		</Card>
	)
}
