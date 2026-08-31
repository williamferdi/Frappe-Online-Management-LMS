import { useMemo, useState } from 'react'
import { ArrowUpRight, CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useCalendar } from '@/hooks/useComms'
import { cn, formatDate, formatTime } from '@/lib/utils'
import type { CalendarEvent, CalendarResponse, EventKind } from '@/types'

const KIND_LABEL: Record<EventKind, string> = {
	class: 'Live class',
	timetable: 'Scheduled',
	session: 'Session',
	fee: 'Payment due',
	term: 'Term',
}

const KIND_DOT: Record<EventKind, string> = {
	class: 'bg-primary',
	timetable: 'bg-primary/60',
	session: 'bg-primary/60',
	fee: 'bg-warning',
	term: 'bg-muted-foreground/50',
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** YYYY-MM-DD in local time. `toISOString` would shift the day in IST. */
function dayKey(date: Date): string {
	const month = String(date.getMonth() + 1).padStart(2, '0')
	const day = String(date.getDate()).padStart(2, '0')
	return `${date.getFullYear()}-${month}-${day}`
}

function monthBounds(anchor: Date) {
	const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
	const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)
	return { first, last }
}

export function Calendar() {
	const [anchor, setAnchor] = useState(() => new Date())
	const { first, last } = monthBounds(anchor)
	const query = useCalendar(dayKey(first), dayKey(last))

	return (
		<QueryState query={query} title="Calendar">
			{(data) => (
				<Loaded
					data={data}
					anchor={anchor}
					onMove={(months) =>
						setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + months, 1))
					}
					onToday={() => setAnchor(new Date())}
				/>
			)}
		</QueryState>
	)
}

function Loaded({
	data,
	anchor,
	onMove,
	onToday,
}: {
	data: CalendarResponse
	anchor: Date
	onMove: (months: number) => void
	onToday: () => void
}) {
	const byDay = useMemo(() => {
		const map = new Map<string, CalendarEvent[]>()
		for (const event of data.events) {
			const key = event.start.slice(0, 10)
			const bucket = map.get(key)
			if (bucket) bucket.push(event)
			else map.set(key, [event])
		}
		return map
	}, [data.events])

	const monthName = anchor.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })

	return (
		<>
			<PageHeader
				title="Calendar"
				description={`${data.events.length} ${data.events.length === 1 ? 'entry' : 'entries'} this month`}
				actions={
					<div className="flex items-center gap-1">
						<Button variant="outline" size="icon" onClick={() => onMove(-1)} aria-label="Previous month">
							<ChevronLeft />
						</Button>
						<Button variant="outline" size="sm" onClick={onToday}>
							Today
						</Button>
						<Button variant="outline" size="icon" onClick={() => onMove(1)} aria-label="Next month">
							<ChevronRight />
						</Button>
					</div>
				}
			/>

			<Card>
				<CardContent className="p-4">
					<div className="mb-3 text-sm font-medium">{monthName}</div>
					<MonthGrid anchor={anchor} byDay={byDay} />
					<Legend />
				</CardContent>
			</Card>

			<Agenda events={data.events} />
		</>
	)
}

function MonthGrid({
	anchor,
	byDay,
}: {
	anchor: Date
	byDay: Map<string, CalendarEvent[]>
}) {
	const { first, last } = monthBounds(anchor)
	// Weeks start Monday, matching the Weekday table the offerings use.
	const lead = (first.getDay() + 6) % 7
	const cells: (Date | null)[] = [
		...Array.from({ length: lead }, () => null),
		...Array.from(
			{ length: last.getDate() },
			(_, i) => new Date(anchor.getFullYear(), anchor.getMonth(), i + 1),
		),
	]
	const today = dayKey(new Date())

	return (
		<div className="grid grid-cols-7 gap-1 text-xs">
			{WEEKDAYS.map((day) => (
				<div key={day} className="text-muted-foreground pb-1 text-center font-medium">
					{day}
				</div>
			))}
			{cells.map((date, index) => {
				if (!date) return <div key={`pad-${index}`} />
				const key = dayKey(date)
				const events = byDay.get(key) ?? []
				return (
					<div
						key={key}
						className={cn(
							'min-h-16 rounded-md border p-1.5',
							key === today && 'border-primary bg-primary/5',
						)}
					>
						<div
							className={cn(
								'tabular-nums',
								key === today ? 'text-primary font-semibold' : 'text-muted-foreground',
							)}
						>
							{date.getDate()}
						</div>
						<div className="mt-1 space-y-0.5">
							{events.slice(0, 3).map((event, i) => (
								<div key={i} className="flex items-center gap-1">
									<span
										className={cn('size-1.5 shrink-0 rounded-full', KIND_DOT[event.kind])}
									/>
									<span className="truncate text-[11px] leading-tight">{event.title}</span>
								</div>
							))}
							{events.length > 3 && (
								<div className="text-muted-foreground text-[11px]">
									+{events.length - 3} more
								</div>
							)}
						</div>
					</div>
				)
			})}
		</div>
	)
}

function Legend() {
	return (
		<div className="text-muted-foreground mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs">
			{(Object.keys(KIND_LABEL) as EventKind[]).map((kind) => (
				<span key={kind} className="flex items-center gap-1.5">
					<span className={cn('size-1.5 rounded-full', KIND_DOT[kind])} />
					{KIND_LABEL[kind]}
				</span>
			))}
		</div>
	)
}

function Agenda({ events }: { events: CalendarEvent[] }) {
	const upcoming = events.filter((event) => event.start.slice(0, 10) >= dayKey(new Date()))

	if (upcoming.length === 0) {
		return (
			<Card className="mt-4">
				<CardContent className="flex flex-col items-center gap-2 py-10 text-center">
					<CalendarDays className="text-muted-foreground size-5" />
					<div className="text-sm font-medium">Nothing left this month</div>
				</CardContent>
			</Card>
		)
	}

	return (
		<Card className="mt-4">
			<CardContent className="p-0">
				<ul className="divide-y">
					{upcoming.map((event, index) => (
						<li
							key={`${event.kind}-${event.reference ?? index}-${event.start}`}
							className="flex flex-wrap items-center gap-3 px-4 py-3"
						>
							<span className={cn('size-2 shrink-0 rounded-full', KIND_DOT[event.kind])} />
							<div className="min-w-0 flex-1">
								<div className="truncate text-sm font-medium">{event.title}</div>
								<div className="text-muted-foreground text-xs">
									{formatDate(event.start.slice(0, 10))}
									{!event.all_day && event.start.length > 10 && (
										<> · {formatTime(event.start.slice(11))}</>
									)}
									{event.detail && <> · {event.detail}</>}
								</div>
							</div>
							<Badge variant="muted">{KIND_LABEL[event.kind]}</Badge>
							{event.url && (
								<Button size="sm" variant="outline" asChild>
									<a href={event.url}>
										Open <ArrowUpRight />
									</a>
								</Button>
							)}
						</li>
					))}
				</ul>
			</CardContent>
		</Card>
	)
}
