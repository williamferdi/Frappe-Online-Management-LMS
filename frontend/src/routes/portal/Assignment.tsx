import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { AssignmentDetail } from '@/components/AssignmentDetail'
import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useCoursework } from '@/hooks/useCoursework'

/**
 * One piece of work: what it asks for, and what has happened to it.
 *
 * Its own address, so a student can keep it, a teacher can send it, and the
 * module item that points at it can point at *it* rather than at the list
 * that contains it.
 *
 * Read out of the coursework payload rather than through an endpoint of its
 * own. That is not only cheaper: it means this page and the list share a
 * cache entry, so handing work in here leaves the list correct without either
 * knowing about the other.
 */
export function Assignment() {
	const { name = null, assignment = null } = useParams()
	const registration = name ? decodeURIComponent(name) : null
	const wanted = assignment ? decodeURIComponent(assignment) : null
	const query = useCoursework(registration)

	return (
		<QueryState query={query} title="Assignment">
			{(data) => {
				const row = data.rows.find((piece) => piece.assignment.name === wanted)
				const back = `/portal/courses/${encodeURIComponent(registration!)}/work`

				if (!row) {
					return (
						<>
							<PageHeader title="Not found" />
							<Card>
								<CardContent className="py-14 text-center">
									<div className="font-medium">
										There is no such piece of work on this course
									</div>
									<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
										It may have been withdrawn, or the link may be for another
										course.
									</p>
									<Button variant="outline" size="sm" className="mt-4" asChild>
										<Link to={back}>All coursework</Link>
									</Button>
								</CardContent>
							</Card>
						</>
					)
				}

				return (
					<>
						<PageHeader
							title={row.assignment.title}
							description={
								data.registration.course_title || data.registration.course_offering
							}
							actions={
								<Button variant="outline" size="sm" asChild>
									<Link to={back}>
										<ArrowLeft /> Coursework
									</Link>
								</Button>
							}
						/>

						<Card>
							<CardContent className="pt-6">
								<AssignmentDetail row={row} registration={registration!} />
							</CardContent>
						</Card>
					</>
				)
			}}
		</QueryState>
	)
}
