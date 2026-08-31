import { useEffect, useState } from 'react'
import { Megaphone, Pin } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { RichText } from '@/components/RichText'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { useAnnouncements, useMarkAnnouncementRead } from '@/hooks/useComms'
import { cn, formatDate } from '@/lib/utils'
import type { Announcement, AnnouncementsResponse } from '@/types'

const CATEGORY_TONE: Record<string, 'default' | 'success' | 'warning' | 'destructive' | 'muted'> = {
	General: 'muted',
	Academic: 'default',
	Finance: 'warning',
	Events: 'success',
	Urgent: 'destructive',
}

export function Announcements() {
	const query = useAnnouncements()

	return (
		<QueryState query={query} title="Announcements">
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: AnnouncementsResponse }) {
	if (data.rows.length === 0) {
		return (
			<>
				<PageHeader title="Announcements" />
				<Card>
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<Megaphone className="text-muted-foreground size-6" />
						<div className="font-medium">No announcements</div>
						<p className="text-muted-foreground max-w-sm text-sm">
							Notices from the college appear here, filtered to your programme, level
							and courses.
						</p>
					</CardContent>
				</Card>
			</>
		)
	}

	return (
		<>
			<PageHeader
				title="Announcements"
				description={data.unread > 0 ? `${data.unread} unread` : 'All caught up'}
			/>
			<ul className="space-y-3">
				{data.rows.map((row) => (
					<Notice key={row.name} notice={row} />
				))}
			</ul>
		</>
	)
}

function Notice({ notice }: { notice: Announcement }) {
	const [open, setOpen] = useState(!notice.read)
	const markRead = useMarkAnnouncementRead()

	// Opening a notice is reading it. Marking it read on render instead would
	// clear the badge for notices the student only scrolled past.
	useEffect(() => {
		if (open && !notice.read && !markRead.isPending) {
			markRead.mutate(notice.name)
		}
		// Only when the panel opens; the mutation identity changes every render.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [open, notice.read, notice.name])

	return (
		<li>
			<Card className={cn(!notice.read && 'border-primary/40')}>
				<CardContent className="p-4">
					<button
						type="button"
						className="flex w-full items-start justify-between gap-3 text-left"
						onClick={() => setOpen((value) => !value)}
						aria-expanded={open}
					>
						<div className="min-w-0">
							<div className="flex flex-wrap items-center gap-2">
								{notice.pinned ? <Pin className="text-primary size-3.5" /> : null}
								<span className="font-medium">{notice.title}</span>
								{!notice.read && <span className="bg-primary size-2 rounded-full" />}
							</div>
							<div className="text-muted-foreground mt-1 text-xs">
								{formatDate(notice.publish_on)}
								{notice.expires_on && <> · until {formatDate(notice.expires_on)}</>}
							</div>
						</div>
						<Badge variant={CATEGORY_TONE[notice.category] ?? 'muted'}>
							{notice.category}
						</Badge>
					</button>

					{open && <RichText html={notice.body} className="mt-3 border-t pt-3" />}
				</CardContent>
			</Card>
		</li>
	)
}
