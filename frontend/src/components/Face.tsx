import { useState } from 'react'

import { cn, initials } from '@/lib/utils'

/**
 * Somebody's photograph in a list, or their initials.
 *
 * A plain `<img>` rather than the Radix avatar: that one holds the image back
 * until it reports as loaded, which means a list of faces renders as a list of
 * initials first and then swaps -- and in a test environment, where nothing
 * ever loads, it renders no image at all. Here the image is in the markup from
 * the start and the initials are what is left if it fails.
 *
 * The files are private. They load on the session the reader already has, so a
 * signed-in officer sees the photograph and anyone else sees the fallback
 * rather than a broken frame.
 */
export function Face({
	name,
	photo,
	className,
}: {
	name: string
	photo: string | null
	className?: string
}) {
	const [failed, setFailed] = useState(false)

	return (
		<span
			className={cn(
				'bg-muted text-muted-foreground inline-flex size-9 shrink-0 select-none items-center justify-center overflow-hidden rounded-lg text-[11px] font-medium',
				className,
			)}
			aria-hidden
		>
			{photo && !failed ? (
				<img
					src={photo}
					alt=""
					className="size-full object-cover"
					onError={() => setFailed(true)}
				/>
			) : (
				initials(name)
			)}
		</span>
	)
}
