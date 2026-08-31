import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu'

import { cn } from '@/lib/utils'

const DropdownMenu = DropdownMenuPrimitive.Root
const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger
const DropdownMenuGroup = DropdownMenuPrimitive.Group

function DropdownMenuContent({
	className,
	sideOffset = 6,
	...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Content>) {
	return (
		<DropdownMenuPrimitive.Portal>
			<DropdownMenuPrimitive.Content
				data-slot="dropdown-menu-content"
				sideOffset={sideOffset}
				className={cn(
					'bg-popover text-popover-foreground z-50 min-w-[10rem] overflow-hidden rounded-lg border p-1 shadow-lg',
					'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
					className,
				)}
				{...props}
			/>
		</DropdownMenuPrimitive.Portal>
	)
}

function DropdownMenuItem({
	className,
	variant = 'default',
	...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Item> & {
	variant?: 'default' | 'destructive'
}) {
	return (
		<DropdownMenuPrimitive.Item
			data-slot="dropdown-menu-item"
			data-variant={variant}
			className={cn(
				'relative flex cursor-default items-center gap-2 rounded-md px-2.5 py-2 text-sm outline-none select-none',
				'focus:bg-muted focus:text-foreground',
				'data-[variant=destructive]:text-destructive data-[variant=destructive]:focus:bg-destructive/10',
				'data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
				"[&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4",
				className,
			)}
			{...props}
		/>
	)
}

function DropdownMenuLabel({
	className,
	...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Label>) {
	return (
		<DropdownMenuPrimitive.Label
			data-slot="dropdown-menu-label"
			className={cn('px-2.5 py-1.5 text-xs font-medium text-muted-foreground', className)}
			{...props}
		/>
	)
}

function DropdownMenuSeparator({
	className,
	...props
}: React.ComponentProps<typeof DropdownMenuPrimitive.Separator>) {
	return (
		<DropdownMenuPrimitive.Separator
			data-slot="dropdown-menu-separator"
			className={cn('bg-border -mx-1 my-1 h-px', className)}
			{...props}
		/>
	)
}

export {
	DropdownMenu,
	DropdownMenuTrigger,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuGroup,
	DropdownMenuSeparator,
}
