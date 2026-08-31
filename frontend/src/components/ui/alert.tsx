import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const alertVariants = cva(
	'relative flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-sm [&>svg]:size-4 [&>svg]:mt-0.5 [&>svg]:shrink-0',
	{
		variants: {
			variant: {
				default: 'bg-card text-foreground',
				info: 'bg-primary/8 border-primary/25 text-foreground [&>svg]:text-primary',
				warning:
					'bg-warning/12 border-warning/35 text-foreground [&>svg]:text-warning-foreground',
				destructive:
					'bg-destructive/8 border-destructive/30 text-foreground [&>svg]:text-destructive',
				success: 'bg-success/10 border-success/30 text-foreground [&>svg]:text-success',
			},
		},
		defaultVariants: { variant: 'default' },
	},
)

function Alert({
	className,
	variant,
	...props
}: React.ComponentProps<'div'> & VariantProps<typeof alertVariants>) {
	return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
}

function AlertTitle({ className, ...props }: React.ComponentProps<'div'>) {
	return <div className={cn('font-medium', className)} {...props} />
}

function AlertDescription({ className, ...props }: React.ComponentProps<'div'>) {
	return <div className={cn('text-muted-foreground text-sm', className)} {...props} />
}

export { Alert, AlertTitle, AlertDescription }
