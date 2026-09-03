import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'
import { initials } from '@/lib/utils'

/**
 * Somebody's photograph in a list, or their initials.
 *
 * The files are private, so the image loads on the session the reader already
 * has; a candidate who never sent a photograph, or a reader without permission
 * on the file, falls back to initials rather than a broken image.
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
	return (
		<Avatar className={cn('size-9 shrink-0 rounded-lg', className)}>
			<AvatarImage src={photo ?? undefined} alt="" className="object-cover" />
			<AvatarFallback className="rounded-lg text-[11px]">{initials(name)}</AvatarFallback>
		</Avatar>
	)
}
