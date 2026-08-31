import { useState, type FormEvent } from 'react'
import { LoaderCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FrappeError, login } from '@/lib/frappe'

export function Login() {
	const [usr, setUsr] = useState('')
	const [pwd, setPwd] = useState('')
	const [busy, setBusy] = useState(false)
	const [error, setError] = useState('')

	async function onSubmit(event: FormEvent) {
		event.preventDefault()
		setBusy(true)
		setError('')
		try {
			// Credentials go straight to Frappe's own login endpoint. Nothing
			// here reads, stores or forwards them anywhere else.
			await login(usr.trim(), pwd)
		} catch (err) {
			setError(
				err instanceof FrappeError && err.status === 401
					? 'That email and password do not match an account.'
					: err instanceof FrappeError
						? err.message
						: 'Could not sign in. Please try again.',
			)
			setBusy(false)
		}
	}

	return (
		<div className="bg-background grid min-h-svh place-items-center px-4 py-10">
			<div className="w-full max-w-sm">
				<div className="mb-7 flex flex-col items-center gap-3 text-center">
					<div
						aria-hidden
						className="bg-primary text-primary-foreground grid size-12 place-items-center rounded-xl font-serif text-xl font-semibold"
					>
						S
					</div>
					<div>
						<h1 className="text-xl font-semibold tracking-tight">
							South India Baptist Bible College
						</h1>
						<p className="text-muted-foreground text-sm">&amp; Seminary — Online</p>
					</div>
				</div>

				<Card>
					<CardContent className="p-6">
						<form onSubmit={onSubmit} className="space-y-4" noValidate>
							<div className="space-y-2">
								<Label htmlFor="usr">Email</Label>
								<Input
									id="usr"
									name="usr"
									type="email"
									autoComplete="username"
									required
									autoFocus
									value={usr}
									onChange={(e) => setUsr(e.target.value)}
									aria-invalid={Boolean(error) || undefined}
								/>
							</div>

							<div className="space-y-2">
								<Label htmlFor="pwd">Password</Label>
								<Input
									id="pwd"
									name="pwd"
									type="password"
									autoComplete="current-password"
									required
									value={pwd}
									onChange={(e) => setPwd(e.target.value)}
									aria-invalid={Boolean(error) || undefined}
								/>
							</div>

							{error && (
								<p role="alert" className="text-destructive text-sm">
									{error}
								</p>
							)}

							<Button type="submit" className="w-full" disabled={busy}>
								{busy && <LoaderCircle className="animate-spin" />}
								{busy ? 'Signing in' : 'Sign in'}
							</Button>
						</form>

						<div className="mt-5 border-t pt-4 text-center">
							<a
								href="/?forgot=1"
								className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-4"
							>
								Forgot your password?
							</a>
						</div>
					</CardContent>
				</Card>

				<p className="text-muted-foreground mt-6 text-center text-xs">
					Applying for admission?{' '}
					<a href="/apply" className="text-primary underline underline-offset-4">
						Start an application
					</a>
				</p>
			</div>
		</div>
	)
}
