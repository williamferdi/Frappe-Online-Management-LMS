/**
 * A donut, drawn as SVG arcs.
 *
 * No chart library: six rings of two to five slices do not justify a
 * dependency, and the whole of the drawing is the arc below.
 *
 * The palette is assigned by the job the colour does, not by taste:
 *
 * * `categorical` — identity (programme, gender). Fixed slot order, never
 *   cycled, validated for colour-vision deficiency at adjacent pairs, which is
 *   the honest pairlist for a ring: a slice only touches its neighbours, and
 *   the legend does the identifying.
 * * `status` — state (active, withdrawn). The reserved status colours, which
 *   are never reused as a series.
 * * `ordinal` — an ordered scale (Level 1→4). One hue, light to dark, so the
 *   order is visible in the colour itself.
 * * `binary` — yes against the rest of the roll, where "no" is the remainder
 *   rather than a competing identity, so it takes a neutral.
 *
 * Every slice is labelled with its count in the legend beneath, so identity is
 * never carried by colour alone — which is also the relief the contrast check
 * requires for the lighter slots on a white surface.
 */
export type DonutKind = 'categorical' | 'status' | 'ordinal' | 'binary'

export interface Slice {
	label: string
	count: number
}

// The slots live in the theme beside the rest of the colours, because the dark
// values are steps chosen for the dark surface rather than a flip of the light
// ones -- and because the app switches theme with a class, which `light-dark()`
// would not follow.
const PALETTE: Record<DonutKind, string[]> = {
	categorical: [
		'var(--viz-cat-1)',
		'var(--viz-cat-2)',
		'var(--viz-cat-3)',
		'var(--viz-cat-4)',
		'var(--viz-cat-5)',
	],
	status: [
		'var(--viz-status-1)',
		'var(--viz-status-2)',
		'var(--viz-status-3)',
		'var(--viz-status-4)',
		'var(--viz-status-5)',
	],
	ordinal: [
		'var(--viz-step-1)',
		'var(--viz-step-2)',
		'var(--viz-step-3)',
		'var(--viz-step-4)',
	],
	binary: ['var(--viz-cat-1)', 'var(--viz-rest)'],
}

const SIZE = 148
const STROKE = 22
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

/** A 2px gap of the surface between segments, as an arc length. */
const GAP = 2

export function Donut({
	title,
	slices,
	kind = 'categorical',
	total,
}: {
	title: string
	slices: Slice[]
	kind?: DonutKind
	total?: number
}) {
	const sum = total ?? slices.reduce((running, slice) => running + slice.count, 0)
	const drawn = slices.filter((slice) => slice.count > 0)

	let offset = 0
	const arcs = drawn.map((slice) => {
		const share = sum > 0 ? slice.count / sum : 0
		const length = Math.max(share * CIRCUMFERENCE - (drawn.length > 1 ? GAP : 0), 0)
		const arc = {
			slice,
			index: slices.indexOf(slice),
			length,
			offset,
			share,
		}
		offset += share * CIRCUMFERENCE
		return arc
	})

	return (
		<figure className="m-0 flex flex-col items-center">
			<figcaption className="border-b w-full pb-2 text-center text-sm font-semibold">
				{title}
			</figcaption>

			<div className="relative py-4">
				<svg
					width={SIZE}
					height={SIZE}
					viewBox={`0 0 ${SIZE} ${SIZE}`}
					role="img"
					aria-label={`${title}: ${slices
						.map((slice) => `${slice.label} ${slice.count}`)
						.join(', ')}`}
				>
					{/* The track, so an empty ring still reads as a ring. */}
					<circle
						cx={SIZE / 2}
						cy={SIZE / 2}
						r={RADIUS}
						fill="none"
						strokeWidth={STROKE}
						className="stroke-muted"
					/>
					<g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
						{arcs.map((arc) => (
							<circle
								key={arc.slice.label}
								cx={SIZE / 2}
								cy={SIZE / 2}
								r={RADIUS}
								fill="none"
								strokeWidth={STROKE}
								stroke={colourFor(kind, arc.index)}
								strokeDasharray={`${arc.length} ${CIRCUMFERENCE - arc.length}`}
								strokeDashoffset={-arc.offset}
							>
								<title>
									{arc.slice.label}: {arc.slice.count} of {sum} (
									{Math.round(arc.share * 100)}%)
								</title>
							</circle>
						))}
					</g>
				</svg>

				<div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
					<span className="text-2xl font-semibold tabular-nums">{sum}</span>
					<span className="text-muted-foreground text-[10px] font-medium uppercase tracking-wider">
						Total
					</span>
				</div>
			</div>

			<ul className="w-full space-y-1.5">
				{slices.map((slice, index) => (
					<li
						key={slice.label}
						className="flex items-center justify-between gap-2 text-xs"
					>
						<span className="flex min-w-0 items-center gap-2">
							<span
								aria-hidden
								className="size-2.5 shrink-0 rounded-full"
								style={{ background: colourFor(kind, index) }}
							/>
							<span className="truncate">{slice.label}</span>
						</span>
						<span className="tabular-nums font-medium">{slice.count}</span>
					</li>
				))}
			</ul>
		</figure>
	)
}

/**
 * The slot for a slice.
 *
 * Keyed on the slice's own position in the declared categories, never on how
 * many slices happen to be drawn: a programme with nobody on it must not
 * repaint the others.
 */
function colourFor(kind: DonutKind, index: number) {
	const slots = PALETTE[kind]
	return slots[index % slots.length]
}
