interface PageHeaderProps {
	title: string
	description?: string
	actions?: React.ReactNode
	/** A portrait, where the page is about one person. */
	avatar?: React.ReactNode
}

export function PageHeader({ title, description, actions, avatar }: PageHeaderProps) {
	return (
		<div className="mb-6 flex flex-wrap items-start justify-between gap-3">
			<div className="flex min-w-0 items-center gap-3">
				{avatar}
				<div className="min-w-0">
					<h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
					{description && (
						<p className="text-muted-foreground mt-1 text-sm">{description}</p>
					)}
				</div>
			</div>
			{actions && <div className="flex items-center gap-2">{actions}</div>}
		</div>
	)
}
