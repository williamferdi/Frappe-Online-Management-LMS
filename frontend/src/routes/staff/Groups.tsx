import { useState } from 'react'
import { LoaderCircle, Plus, Trash2, Users } from 'lucide-react'
import { toast } from 'sonner'

import { QueryState } from '@/components/QueryState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
	useDeleteGroup,
	useGroupSets,
	useSaveGroup,
	useSaveGroupSet,
} from '@/hooks/useCollaboration'
import { FrappeError } from '@/lib/frappe'
import type { CourseGroup, GroupSet, GroupSetsResponse } from '@/types'

function message(error: unknown) {
	return error instanceof FrappeError ? error.message : 'Something went wrong.'
}

/**
 * Group sets for one course.
 *
 * A set is a partition: a student is in one group of it or none. That is
 * enforced on the server, because a differentiated date resolved through
 * groups would otherwise depend on which group happened to be read first.
 */
export function Groups({ offering }: { offering: string }) {
	const query = useGroupSets(offering)

	return (
		<QueryState query={query} title="Groups">
			{(data) => <Sets data={data} offering={offering} />}
		</QueryState>
	)
}

function Sets({ data, offering }: { data: GroupSetsResponse; offering: string }) {
	const [adding, setAdding] = useState(false)
	const [title, setTitle] = useState('')
	const [limit, setLimit] = useState('')
	const save = useSaveGroupSet(offering)

	return (
		<div className="space-y-4">
			{adding ? (
				<Card>
					<CardContent className="flex flex-wrap items-end gap-3 p-4">
						<div>
							<Label htmlFor="set-title">Set name</Label>
							<Input
								id="set-title"
								className="mt-1 w-56"
								placeholder="Seminar groups"
								value={title}
								onChange={(event) => setTitle(event.target.value)}
							/>
						</div>
						<div>
							<Label htmlFor="set-limit">Members per group</Label>
							<Input
								id="set-limit"
								type="number"
								className="mt-1 w-40"
								placeholder="0 for no limit"
								value={limit}
								onChange={(event) => setLimit(event.target.value)}
							/>
						</div>
						<Button
							size="sm"
							disabled={!title || save.isPending}
							onClick={() =>
								save.mutate(
									{ title, group_limit: Number(limit) || 0 },
									{
										onSuccess: () => {
											toast.success('Group set created')
											setTitle('')
											setLimit('')
											setAdding(false)
										},
										onError: (error) => toast.error(message(error)),
									},
								)
							}
						>
							{save.isPending ? <LoaderCircle className="animate-spin" /> : null}
							Create
						</Button>
						<Button variant="outline" size="sm" onClick={() => setAdding(false)}>
							Cancel
						</Button>
					</CardContent>
				</Card>
			) : (
				<Button size="sm" onClick={() => setAdding(true)}>
					<Plus /> New group set
				</Button>
			)}

			{data.sets.length === 0 ? (
				<Card>
					<CardContent className="py-14 text-center">
						<Users className="text-muted-foreground mx-auto mb-3 size-8" />
						<div className="font-medium">No groups yet</div>
						<p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">
							A group set divides the class up. A student is in one group of each
							set, so a set can carry its own deadlines.
						</p>
					</CardContent>
				</Card>
			) : (
				data.sets.map((set) => (
					<SetCard key={set.name} set={set} data={data} offering={offering} />
				))
			)}
		</div>
	)
}

function SetCard({
	set,
	data,
	offering,
}: {
	set: GroupSet
	data: GroupSetsResponse
	offering: string
}) {
	const [adding, setAdding] = useState(false)

	// Everyone already in a group of this set, so the picker cannot offer a
	// student the server would refuse.
	const taken = new Set(
		set.groups.flatMap((group) => group.members.map((member) => member.course_registration)),
	)
	const free = data.roster.filter((row) => !taken.has(row.name))

	return (
		<Card>
			<CardContent className="p-0">
				<div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
					<span className="font-medium">{set.title}</span>
					{set.group_limit > 0 && (
						<Badge variant="secondary">max {set.group_limit}</Badge>
					)}
					<span className="text-muted-foreground text-xs">
						{free.length} not in a group
					</span>
					<Button
						variant="outline"
						size="sm"
						className="ml-auto"
						onClick={() => setAdding(!adding)}
					>
						<Plus /> Group
					</Button>
				</div>

				{adding && (
					<div className="border-b px-4 py-3">
						<GroupForm
							set={set}
							free={free}
							offering={offering}
							onDone={() => setAdding(false)}
						/>
					</div>
				)}

				{set.groups.length === 0 ? (
					<p className="text-muted-foreground px-4 py-6 text-sm">
						No groups in this set yet.
					</p>
				) : (
					<ul className="divide-y">
						{set.groups.map((group) => (
							<GroupRow key={group.name} group={group} offering={offering} />
						))}
					</ul>
				)}
			</CardContent>
		</Card>
	)
}

function GroupRow({ group, offering }: { group: CourseGroup; offering: string }) {
	const remove = useDeleteGroup(offering)

	return (
		<li className="flex flex-wrap items-center gap-2 px-4 py-2.5">
			<span className="w-32 shrink-0 text-sm font-medium">{group.title}</span>
			<span className="text-muted-foreground min-w-0 flex-1 truncate text-sm">
				{group.members.length === 0
					? 'Nobody yet'
					: group.members.map((member) => member.student_name).join(', ')}
			</span>
			<Button
				variant="ghost"
				size="icon"
				aria-label={`Delete ${group.title}`}
				onClick={() =>
					remove.mutate(group.name, {
						onSuccess: () => toast.success('Group deleted'),
						onError: (error) => toast.error(message(error)),
					})
				}
			>
				<Trash2 className="size-4" />
			</Button>
		</li>
	)
}

function GroupForm({
	set,
	free,
	offering,
	onDone,
}: {
	set: GroupSet
	free: { name: string; student_name: string | null }[]
	offering: string
	onDone: () => void
}) {
	const [title, setTitle] = useState(`Group ${set.groups.length + 1}`)
	const [members, setMembers] = useState<string[]>([])
	const save = useSaveGroup(offering)

	return (
		<div className="space-y-3">
			<div>
				<Label htmlFor={`group-title-${set.name}`}>Group name</Label>
				<Input
					id={`group-title-${set.name}`}
					className="mt-1 w-56"
					value={title}
					onChange={(event) => setTitle(event.target.value)}
				/>
			</div>

			<fieldset>
				<legend className="text-xs font-medium">Members</legend>
				<div className="mt-1 flex flex-wrap gap-2">
					{free.length === 0 ? (
						<span className="text-muted-foreground text-sm">
							Everybody is already in a group of this set.
						</span>
					) : (
						free.map((row) => (
							<label
								key={row.name}
								className="border-input hover:bg-muted flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1 text-sm"
							>
								<input
									type="checkbox"
									checked={members.includes(row.name)}
									onChange={() =>
										setMembers(
											members.includes(row.name)
												? members.filter((value) => value !== row.name)
												: [...members, row.name],
										)
									}
								/>
								{row.student_name}
							</label>
						))
					)}
				</div>
			</fieldset>

			<div className="flex justify-end gap-2">
				<Button variant="outline" size="sm" onClick={onDone}>
					Cancel
				</Button>
				<Button
					size="sm"
					disabled={!title || save.isPending}
					onClick={() =>
						save.mutate(
							{ group_set: set.name, title, members },
							{
								onSuccess: () => {
									toast.success('Group created')
									onDone()
								},
								onError: (error) => toast.error(message(error)),
							},
						)
					}
				>
					Create
				</Button>
			</div>
		</div>
	)
}
