import { useParams } from 'react-router-dom'

import { ModuleOutline } from '@/components/ModuleOutline'
import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Card, CardContent } from '@/components/ui/card'
import { useMyCourse } from '@/hooks/useSyllabus'
import type { CourseOutline } from '@/types'

/**
 * A student's course as a list of modules: what is in it, in what order, and
 * what is open.
 *
 * An index and nothing more. A row leads to the player, which is where a
 * lesson is actually read -- and where the notes, the bookmark, the thread,
 * the next and previous, and marking something done already live. Opening a
 * lesson in place here meant a second, poorer reader with none of that, and
 * two places that both had to learn every new item type.
 */
export function MyCourse() {
	const { name = null } = useParams()
	const registration = name ? decodeURIComponent(name) : null
	const query = useMyCourse(registration)

	return (
		<QueryState query={query} title="Course">
			{(data) => <Loaded data={data} registration={registration!} />}
		</QueryState>
	)
}

function Loaded({
	data,
	registration,
}: {
	data: CourseOutline
	registration: string
}) {
	return (
		<>
			<PageHeader
				title={data.registration.course_title || data.registration.course_offering}
				description={
					data.modules.length === 1 ? '1 module' : `${data.modules.length} modules`
				}
			/>

			{data.modules.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<div className="font-medium">Nothing here yet</div>
						<p className="text-muted-foreground mt-1 text-sm">
							Modules appear as your teacher publishes them.
						</p>
					</CardContent>
				</Card>
			) : (
				<ModuleOutline
					modules={data.modules}
					itemHref={(item) =>
						`/portal/courses/${encodeURIComponent(registration)}/learn/${encodeURIComponent(item.name)}`
					}
					// A locked row is not a link. The player would refuse it, and
					// being refused after a click is worse than not being offered.
					canOpen={(item) => !item.locked}
				/>
			)}
		</>
	)
}
