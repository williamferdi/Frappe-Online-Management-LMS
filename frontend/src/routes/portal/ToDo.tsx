import { Link } from 'react-router-dom'
import {
	ArrowUpRight,
	CheckCircle2,
	CreditCard,
	FileText,
	Lock,
	PenLine,
	type LucideIcon,
} from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useTodo } from '@/hooks/useComms'
import { cn, formatDate } from '@/lib/utils'
import type { TodoItem, TodoKind, TodoResponse } from '@/types'

const ICONS: Record<TodoKind, LucideIcon> = {
	fee: CreditCard,
	blocked: Lock,
	assignment: FileText,
	registration: PenLine,
}

const LABELS: Record<TodoKind, string> = {
	fee: 'Payment',
	blocked: 'Blocked',
	assignment: 'Assignment',
	registration: 'Registration',
}

export function ToDo() {
	const query = useTodo()

	return (
		<QueryState query={query} title="To Do">
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: TodoResponse }) {
	if (data.count === 0) {
		return (
			<>
				<PageHeader title="To Do" />
				<Card>
					<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
						<CheckCircle2 className="text-success size-7" />
						<div className="font-medium">Nothing outstanding</div>
						<p className="text-muted-foreground max-w-sm text-sm">
							No fees due, no assignments waiting and nothing to register for. This
							list is assembled from your record, so it fills itself when something
							needs you.
						</p>
					</CardContent>
				</Card>
			</>
		)
	}

	return (
		<>
			<PageHeader
				title="To Do"
				description={
					data.urgent > 0
						? `${data.count} outstanding, ${data.urgent} needing attention now`
						: `${data.count} outstanding`
				}
			/>
			<ul className="space-y-2.5">
				{data.items.map((item, index) => (
					<Item key={`${item.kind}-${item.reference ?? index}`} item={item} />
				))}
			</ul>
		</>
	)
}

function Item({ item }: { item: TodoItem }) {
	const Icon = ICONS[item.kind] ?? FileText
	const overdue = Boolean(item.urgent)
	const internal = item.url?.startsWith('/portal')

	return (
		<li>
			<Card className={cn(overdue && 'border-destructive/40')}>
				<CardContent className="flex flex-wrap items-center gap-4 p-4">
					<div
						className={cn(
							'grid size-9 shrink-0 place-items-center rounded-lg',
							overdue ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground',
						)}
					>
						<Icon className="size-4" />
					</div>

					<div className="min-w-0 flex-1">
						<div className="flex flex-wrap items-center gap-2">
							<span className="font-medium">{item.title}</span>
							<Badge variant={overdue ? 'destructive' : 'muted'}>
								{LABELS[item.kind] ?? item.kind}
							</Badge>
						</div>
						<div className="text-muted-foreground mt-0.5 text-sm">{item.detail}</div>
						{item.due && (
							<div
								className={cn(
									'mt-1 text-xs',
									overdue ? 'text-destructive font-medium' : 'text-muted-foreground',
								)}
							>
								{overdue ? 'Overdue — due ' : 'Due '}
								{formatDate(item.due)}
							</div>
						)}
					</div>

					{item.url &&
						(internal ? (
							<Button size="sm" asChild>
								<Link to={item.url}>Open</Link>
							</Button>
						) : (
							<Button size="sm" asChild>
								<a href={item.url}>
									Open <ArrowUpRight />
								</a>
							</Button>
						))}
				</CardContent>
			</Card>
		</li>
	)
}
