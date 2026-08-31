import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'

const Dialog = DialogPrimitive.Root
const DialogTrigger = DialogPrimitive.Trigger
const DialogClose = DialogPrimitive.Close

function DialogContent({
	className,
	children,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
	return (
		<DialogPrimitive.Portal>
			<DialogPrimitive.Overlay className="bg-foreground/30 fixed inset-0 z-50 backdrop-blur-[2px]" />
			<DialogPrimitive.Content
				className={cn(
					'bg-card fixed left-1/2 top-1/2 z-50 grid w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl border p-6 shadow-lg',
					className,
				)}
				{...props}
			>
				{children}
				<DialogPrimitive.Close
					className="hover:bg-muted absolute right-4 top-4 rounded-md p-1 transition-colors"
					aria-label="Close"
				>
					<X className="size-4" />
				</DialogPrimitive.Close>
			</DialogPrimitive.Content>
		</DialogPrimitive.Portal>
	)
}

function DialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
	return <div className={cn('flex flex-col gap-1.5 pr-6', className)} {...props} />
}

function DialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
	return (
		<div
			className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end', className)}
			{...props}
		/>
	)
}

function DialogTitle({
	className,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
	return (
		<DialogPrimitive.Title
			className={cn('text-lg font-semibold leading-none tracking-tight', className)}
			{...props}
		/>
	)
}

function DialogDescription({
	className,
	...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
	return (
		<DialogPrimitive.Description
			className={cn('text-muted-foreground text-sm', className)}
			{...props}
		/>
	)
}

export {
	Dialog,
	DialogTrigger,
	DialogClose,
	DialogContent,
	DialogHeader,
	DialogFooter,
	DialogTitle,
	DialogDescription,
}
