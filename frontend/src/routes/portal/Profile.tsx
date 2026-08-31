import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Camera, Info, LoaderCircle } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/PageHeader'
import { QueryState } from '@/components/QueryState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useProfile, useUpdatePhoto, useUpdateProfile } from '@/hooks/useStudent'
import { FrappeError } from '@/lib/frappe'
import { formatDate, initials } from '@/lib/utils'
import type { ProfileResponse } from '@/types'

export function Profile() {
	const query = useProfile()

	return (
		<QueryState query={query} title="Profile">
			{(data) => <Loaded data={data} />}
		</QueryState>
	)
}

function Loaded({ data }: { data: ProfileResponse }) {
	const student = data.student
	const enrollment = data.enrollment

	return (
		<>
			<PageHeader title="Profile" />

			{!student && (
				<Alert variant="info" className="mb-5">
					<Info />
					<AlertDescription>
						Your account is not linked to a student record yet, so only your sign-in
						details are shown.
					</AlertDescription>
				</Alert>
			)}

			<div className="grid gap-4 lg:grid-cols-3">
				<Card className="lg:col-span-1">
					<CardContent className="flex flex-col items-center gap-3 p-6 text-center">
						<PhotoPicker
							name={student?.full_name || data.user.full_name || data.user.name}
							photo={student?.photo || data.user.user_image || null}
							canEdit={Boolean(student)}
						/>
						<div>
							<div className="font-semibold">
								{student?.full_name || data.user.full_name}
							</div>
							<div className="text-muted-foreground text-sm">{data.user.name}</div>
						</div>
						{student && <Badge variant="muted">{student.status}</Badge>}
					</CardContent>
				</Card>

				<div className="space-y-4 lg:col-span-2">
					{student && <ContactForm student={student} />}

					<Card>
						<CardHeader>
							<CardTitle className="text-base">College record</CardTitle>
						</CardHeader>
						<CardContent className="pt-3">
							<dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
								<Field label="Student ID" value={student?.name} mono />
								<Field label="Programme" value={enrollment?.program_name} />
								<Field label="Level" value={enrollment?.current_level} />
								<Field
									label="Expected completion"
									value={
										enrollment?.expected_completion
											? formatDate(enrollment.expected_completion)
											: undefined
									}
								/>
								<Field label="Date of birth" value={formatDate(student?.dob)} />
								<Field label="Gender" value={student?.gender} />
								<Field label="Email" value={student?.email} />
							</dl>
							<p className="text-muted-foreground mt-4 text-xs">
								These are the Registrar's record of who you are. To correct any of
								them, write to the Registrar's office — they cannot be changed here.
							</p>
						</CardContent>
					</Card>
				</div>
			</div>
		</>
	)
}

/** Only what the college uses to reach you. Everything else is the office's. */
function ContactForm({ student }: { student: NonNullable<ProfileResponse['student']> }) {
	const update = useUpdateProfile()
	const [mobile, setMobile] = useState(student.mobile ?? '')
	const [whatsapp, setWhatsapp] = useState(student.whatsapp ?? '')
	const [address, setAddress] = useState(student.address ?? '')

	// A refetch after saving replaces the record; without this the inputs keep
	// showing whatever was typed rather than what the server stored.
	useEffect(() => {
		setMobile(student.mobile ?? '')
		setWhatsapp(student.whatsapp ?? '')
		setAddress(student.address ?? '')
	}, [student.mobile, student.whatsapp, student.address])

	const dirty =
		mobile !== (student.mobile ?? '') ||
		whatsapp !== (student.whatsapp ?? '') ||
		address !== (student.address ?? '')

	function onSubmit(event: FormEvent) {
		event.preventDefault()
		update.mutate(
			{ mobile, whatsapp, address },
			{
				onSuccess: () => toast.success('Contact details saved'),
				onError: (error) =>
					toast.error(
						error instanceof FrappeError ? error.message : 'Could not save your details.',
					),
			},
		)
	}

	return (
		<Card>
			<CardHeader>
				<CardTitle className="text-base">Contact details</CardTitle>
			</CardHeader>
			<CardContent className="pt-3">
				<form onSubmit={onSubmit} className="space-y-4" noValidate>
					<div className="grid gap-4 sm:grid-cols-2">
						<div className="space-y-2">
							<Label htmlFor="mobile">Mobile</Label>
							<Input
								id="mobile"
								value={mobile}
								inputMode="tel"
								onChange={(e) => setMobile(e.target.value)}
							/>
						</div>
						<div className="space-y-2">
							<Label htmlFor="whatsapp">WhatsApp</Label>
							<Input
								id="whatsapp"
								value={whatsapp}
								inputMode="tel"
								onChange={(e) => setWhatsapp(e.target.value)}
							/>
						</div>
					</div>

					<div className="space-y-2">
						<Label htmlFor="address">Address</Label>
						<Textarea
							id="address"
							value={address}
							onChange={(e) => setAddress(e.target.value)}
						/>
					</div>

					<div className="flex justify-end">
						<Button type="submit" disabled={!dirty || update.isPending}>
							{update.isPending && <LoaderCircle className="animate-spin" />}
							Save changes
						</Button>
					</div>
				</form>
			</CardContent>
		</Card>
	)
}

function PhotoPicker({
	name,
	photo,
	canEdit,
}: {
	name: string
	photo: string | null
	canEdit: boolean
}) {
	const input = useRef<HTMLInputElement>(null)
	const upload = useUpdatePhoto()

	function onPick(file: File | undefined) {
		if (!file) return
		upload.mutate(file, {
			onSuccess: () => toast.success('Photograph updated'),
			onError: (error) =>
				toast.error(
					error instanceof FrappeError ? error.message : 'That photograph was not accepted.',
				),
		})
	}

	return (
		<div className="relative">
			<Avatar className="size-24">
				{photo && <AvatarImage src={photo} alt="" />}
				<AvatarFallback className="text-2xl">{initials(name)}</AvatarFallback>
			</Avatar>

			{canEdit && (
				<>
					<input
						ref={input}
						type="file"
						accept="image/jpeg,image/png"
						className="sr-only"
						onChange={(e) => onPick(e.target.files?.[0])}
					/>
					<Button
						size="icon"
						variant="outline"
						className="absolute -bottom-1 -right-1 size-8 rounded-full"
						onClick={() => input.current?.click()}
						disabled={upload.isPending}
						aria-label="Change photograph"
					>
						{upload.isPending ? (
							<LoaderCircle className="animate-spin" />
						) : (
							<Camera className="size-3.5" />
						)}
					</Button>
				</>
			)}
		</div>
	)
}

function Field({
	label,
	value,
	mono,
}: {
	label: string
	value: string | null | undefined
	mono?: boolean
}) {
	return (
		<div>
			<dt className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
				{label}
			</dt>
			<dd className={mono ? 'font-mono text-sm' : 'text-sm'}>{value || '—'}</dd>
		</div>
	)
}
