import { useState } from 'react'
import {
	Info,
	LoaderCircle,
	Plus,
	Search,
	ShieldAlert,
	Users as UsersIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from '@/components/ui/table'
import { useDebounced } from '@/hooks/useDebounced'
import {
	useCreateUser,
	useRoleSummary,
	useSetEnabled,
	useSetRoles,
	useUsers,
} from '@/hooks/useFinance'
import { boot, FrappeError } from '@/lib/frappe'
import { cn, formatDate } from '@/lib/utils'
import type { UserRow } from '@/types'

export function Users() {
	const [search, setSearch] = useState('')
	const [editing, setEditing] = useState<UserRow | null>(null)
	const [creating, setCreating] = useState(false)
	const debounced = useDebounced(search, 300)
	const query = useUsers({ search: debounced })
	const summary = useRoleSummary()

	return (
		<>
			<PageHeader
			title="Users"
			description="Accounts and what they may do"
			actions={
				<Button size="sm" onClick={() => setCreating(true)}>
					<Plus /> New account
				</Button>
			}
		/>

			{/* An empty role is not a curiosity: with nobody holding Registrar a
			    student's message has nowhere to go and no promotion can be
			    approved. Worth showing before anybody has to ask why. */}
			{summary.data && summary.data.some((row) => row.count === 0) && (
				<Alert variant="warning" className="mb-4">
					<ShieldAlert />
					<AlertDescription>
						Nobody holds{' '}
						<b>
							{summary.data
								.filter((row) => row.count === 0)
								.map((row) => row.role)
								.join(', ')}
						</b>
						. Work that needs those roles cannot be done, and portal messages to
						the office have nowhere to arrive.
					</AlertDescription>
				</Alert>
			)}

			<QueryState query={query} title="Users">
				{(data) => (
					<>
						<div className="mb-4 flex flex-wrap items-center gap-2">
							<div className="relative min-w-56 flex-1">
								<Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" />
								<Input
									value={search}
									onChange={(event) => setSearch(event.target.value)}
									placeholder="Name or email"
									className="pl-9"
									aria-label="Search accounts"
								/>
							</div>
						</div>

						{summary.data && <RoleCounts rows={summary.data} />}

						{data.rows.length === 0 ? (
							<Card className="mt-4">
								<CardContent className="flex flex-col items-center gap-2 py-14 text-center">
									<UsersIcon className="text-muted-foreground size-6" />
									<div className="font-medium">No accounts match</div>
								</CardContent>
							</Card>
						) : (
							<Card className="mt-4">
								<CardContent className="p-0">
									<Table>
										<TableHeader>
											<TableRow>
												<TableHead className="pl-5">Account</TableHead>
												<TableHead>Roles</TableHead>
												<TableHead>Last active</TableHead>
												<TableHead className="pr-5 text-right">Access</TableHead>
											</TableRow>
										</TableHeader>
										<TableBody>
											{data.rows.map((row) => (
												<Row key={row.name} row={row} onEdit={() => setEditing(row)} />
											))}
										</TableBody>
									</Table>
								</CardContent>
							</Card>
						)}

						<RolesDialog
							row={editing}
							managed={data.managed_roles}
							onClose={() => setEditing(null)}
						/>

						<NewUserDialog
							open={creating}
							managed={data.managed_roles}
							onClose={() => setCreating(false)}
						/>
					</>
				)}
			</QueryState>
		</>
	)
}

function RoleCounts({ rows }: { rows: { role: string; count: number }[] }) {
	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Who holds what</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<div className="flex flex-wrap gap-2">
					{rows.map((row) => (
						<div
							key={row.role}
							className={cn(
								'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs',
								row.count === 0 ? 'bg-warning/12' : 'bg-muted/60',
							)}
						>
							<span>{row.role}</span>
							<span className="font-semibold tabular-nums">{row.count}</span>
						</div>
					))}
				</div>
			</CardContent>
		</Card>
	)
}

function Row({ row, onEdit }: { row: UserRow; onEdit: () => void }) {
	const setEnabled = useSetEnabled()
	const isSelf = row.name === boot.user

	return (
		<TableRow className={cn(!row.enabled && 'opacity-60')}>
			<TableCell className="pl-5">
				<div className="font-medium">{row.full_name}</div>
				<div className="text-muted-foreground text-xs">
					{row.name}
					{row.student && <> · {row.student}</>}
				</div>
			</TableCell>
			<TableCell>
				<div className="flex flex-wrap gap-1">
					{row.protected_roles.map((role) => (
						<Badge key={role} variant="destructive">
							{role}
						</Badge>
					))}
					{row.roles.map((role) => (
						<Badge key={role} variant="default">
							{role}
						</Badge>
					))}
					{row.roles.length === 0 && row.protected_roles.length === 0 && (
						<span className="text-muted-foreground text-xs">No roles</span>
					)}
				</div>
			</TableCell>
			<TableCell className="text-muted-foreground text-xs">
				{row.last_active ? formatDate(row.last_active) : 'Never'}
			</TableCell>
			<TableCell className="pr-5 text-right">
				<div className="flex items-center justify-end gap-1">
					<Button size="sm" variant="outline" onClick={onEdit}>
						Roles
					</Button>
					<Button
						size="sm"
						variant="ghost"
						disabled={isSelf || setEnabled.isPending}
						title={isSelf ? 'You cannot disable your own account' : undefined}
						onClick={() =>
							setEnabled.mutate(
								{ user: row.name, enabled: row.enabled ? 0 : 1 },
								{
									onSuccess: () =>
										toast.success(row.enabled ? 'Account disabled' : 'Account enabled'),
									onError: (error) =>
										toast.error(
											error instanceof FrappeError ? error.message : 'That did not work.',
										),
								},
							)
						}
					>
						{row.enabled ? 'Disable' : 'Enable'}
					</Button>
				</div>
			</TableCell>
		</TableRow>
	)
}

function RolesDialog({
	row,
	managed,
	onClose,
}: {
	row: UserRow | null
	managed: string[]
	onClose: () => void
}) {
	const setRoles = useSetRoles()
	const [chosen, setChosen] = useState<string[]>([])
	const [seeded, setSeeded] = useState<string | null>(null)

	// Seed from the row the first time this account is opened, not on every
	// render, or ticking a box would be undone by the next one.
	if (row && seeded !== row.name) {
		setSeeded(row.name)
		setChosen(row.roles)
	}

	function toggle(role: string) {
		setChosen((current) =>
			current.includes(role) ? current.filter((r) => r !== role) : [...current, role],
		)
	}

	function save() {
		if (!row) return
		setRoles.mutate(
			{ user: row.name, roles: chosen },
			{
				onSuccess: () => {
					onClose()
					toast.success(`Roles updated for ${row.full_name}`)
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'Those roles were not saved.',
					),
			},
		)
	}

	return (
		<Dialog open={Boolean(row)} onOpenChange={(open) => !open && onClose()}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>{row?.full_name}</DialogTitle>
					<DialogDescription>{row?.name}</DialogDescription>
				</DialogHeader>

				{row && row.protected_roles.length > 0 && (
					<Alert variant="warning">
						<Info />
						<AlertDescription>
							This account also holds <b>{row.protected_roles.join(', ')}</b>, which is
							not managed here and is left untouched.
						</AlertDescription>
					</Alert>
				)}

				<div className="grid gap-1.5 sm:grid-cols-2">
					{managed.map((role) => (
						<label
							key={role}
							className="hover:bg-muted flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm"
						>
							<input
								type="checkbox"
								checked={chosen.includes(role)}
								onChange={() => toggle(role)}
								className="size-3.5"
							/>
							{role}
						</label>
					))}
				</div>

				<p className="text-muted-foreground text-xs">
					Passwords are not managed here. Send a reset from Frappe Desk, or let the
					person use the forgotten-password link.
				</p>

				<DialogFooter>
					<Button variant="outline" onClick={onClose} disabled={setRoles.isPending}>
						Cancel
					</Button>
					<Button onClick={save} disabled={setRoles.isPending}>
						{setRoles.isPending && <LoaderCircle className="animate-spin" />}
						Save roles
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	)
}


function NewUserDialog({
	open,
	managed,
	onClose,
}: {
	open: boolean
	managed: string[]
	onClose: () => void
}) {
	const create = useCreateUser()
	const [email, setEmail] = useState('')
	const [firstName, setFirstName] = useState('')
	const [lastName, setLastName] = useState('')
	const [roles, setRoles] = useState<string[]>([])

	function submit() {
		create.mutate(
			{ email: email.trim(), first_name: firstName.trim(), last_name: lastName.trim() || undefined, roles },
			{
				onSuccess: () => {
					setEmail('')
					setFirstName('')
					setLastName('')
					setRoles([])
					onClose()
					toast.success('Account created', {
						description: 'They will get a welcome email with a link to set their own password.',
					})
				},
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'That account was not created.',
					),
			},
		)
	}

	return (
		<Dialog open={open} onOpenChange={(next) => !next && onClose()}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>New account</DialogTitle>
					<DialogDescription>
						Frappe emails them a link to set their own password, so nobody here
						ever chooses or sees it.
					</DialogDescription>
				</DialogHeader>

				<div className="space-y-2">
					<Label htmlFor="new-email">Email</Label>
					<Input
						id="new-email"
						type="email"
						value={email}
						autoFocus
						onChange={(event) => setEmail(event.target.value)}
					/>
				</div>

				<div className="grid gap-4 sm:grid-cols-2">
					<div className="space-y-2">
						<Label htmlFor="new-first">First name</Label>
						<Input id="new-first" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
					</div>
					<div className="space-y-2">
						<Label htmlFor="new-last">Last name</Label>
						<Input id="new-last" value={lastName} onChange={(e) => setLastName(e.target.value)} />
					</div>
				</div>

				<div className="grid gap-1.5 sm:grid-cols-2">
					{managed.map((role) => (
						<label
							key={role}
							className="hover:bg-muted flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm"
						>
							<input
								type="checkbox"
								checked={roles.includes(role)}
								onChange={() =>
									setRoles((current) =>
										current.includes(role)
											? current.filter((r) => r !== role)
											: [...current, role],
									)
								}
								className="size-3.5"
							/>
							{role}
						</label>
					))}
				</div>

				<DialogFooter>
					<Button variant="outline" onClick={onClose} disabled={create.isPending}>
						Cancel
					</Button>
					<Button
						onClick={submit}
						disabled={!email.trim() || !firstName.trim() || create.isPending}
					>
						{create.isPending && <LoaderCircle className="animate-spin" />}
						Create
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	)
}
