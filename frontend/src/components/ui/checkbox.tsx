import { cn } from '@/lib/utils'

/**
 * A checkbox.
 *
 * The native input rather than a Radix one: it is a checkbox, the browser
 * already gives it the keyboard behaviour, the indeterminate state and the
 * label association, and `accent-color` styles it to the theme in one line.
 */
export function Checkbox({
	className,
	...props
}: Omit<React.ComponentProps<'input'>, 'type'>) {
	return (
		<input
			type="checkbox"
			data-slot="checkbox"
			className={cn(
				'accent-primary size-4 shrink-0 cursor-pointer rounded-sm align-middle',
				'focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-2',
				'disabled:cursor-not-allowed disabled:opacity-50',
				className,
			)}
			{...props}
		/>
	)
}
