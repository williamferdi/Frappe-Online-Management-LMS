import * as ProgressPrimitive from '@radix-ui/react-progress'

import { cn } from '@/lib/utils'

function Progress({
	className,
	value = 0,
	...props
}: React.ComponentProps<typeof ProgressPrimitive.Root>) {
	const pct = Math.min(Math.max(value ?? 0, 0), 100)
	return (
		<ProgressPrimitive.Root
			className={cn('bg-muted relative h-1.5 w-full overflow-hidden rounded-full', className)}
			value={pct}
			{...props}
		>
			<ProgressPrimitive.Indicator
				className="bg-primary h-full w-full flex-1 transition-transform"
				style={{ transform: `translateX(-${100 - pct}%)` }}
			/>
		</ProgressPrimitive.Root>
	)
}

export { Progress }
