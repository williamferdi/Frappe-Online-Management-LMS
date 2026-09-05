import { useState } from 'react'

/**
 * Reordering a list by dragging, on the browser's own drag and drop.
 *
 * No library: the bundle is committed to git, so a dependency is a permanent
 * addition to what the portal ships, and a vertical list needs five event
 * handlers.
 *
 * **Dragging is not the only way to do this.** Native drag and drop cannot be
 * driven from a keyboard at all, so every list that uses this keeps its move
 * buttons — the drag is the fast path for a mouse, not the only path.
 *
 * The new order is computed and sent whole rather than as a swap, so a
 * half-applied reorder cannot leave two things claiming the same position —
 * the same reason `syllabus.reorder` rewrites positions from the list it is
 * given.
 */
export function useDragOrder(
	names: string[],
	onReorder: (order: string[]) => void,
) {
	const [dragging, setDragging] = useState<string | null>(null)
	const [over, setOver] = useState<string | null>(null)

	const reset = () => {
		setDragging(null)
		setOver(null)
	}

	const move = (from: number, to: number) => {
		if (from === to || from < 0 || to < 0 || to >= names.length) return
		const order = [...names]
		order.splice(to, 0, order.splice(from, 1)[0])
		onReorder(order)
	}

	return {
		dragging,
		over,

		/** Move by keyboard, which dragging cannot do. */
		moveBy: (name: string, by: number) => {
			const from = names.indexOf(name)
			move(from, from + by)
		},

		handlers: (name: string) => ({
			draggable: true,
			onDragStart: (event: React.DragEvent) => {
				setDragging(name)
				event.dataTransfer.effectAllowed = 'move'
				// Firefox will not start a drag without data set on it.
				event.dataTransfer.setData('text/plain', name)
			},
			onDragOver: (event: React.DragEvent) => {
				// Without preventDefault the drop never fires — the browser's
				// default is to refuse.
				event.preventDefault()
				event.dataTransfer.dropEffect = 'move'
				if (name !== over) setOver(name)
			},
			onDragLeave: () => {
				if (name === over) setOver(null)
			},
			onDrop: (event: React.DragEvent) => {
				event.preventDefault()
				const held = dragging ?? event.dataTransfer.getData('text/plain')
				if (held && held !== name) {
					move(names.indexOf(held), names.indexOf(name))
				}
				reset()
			},
			onDragEnd: reset,
		}),
	}
}
