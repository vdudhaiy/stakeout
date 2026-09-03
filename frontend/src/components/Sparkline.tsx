import { motion } from 'motion/react'

interface Props {
  points: number[]
  width?: number
  height?: number
  className?: string
}

/** Minimal inline trend line — no axes/tooltips/margins, just a shape. For
 * one-per-list-item use (e.g. PeersPanel chips) where pulling in recharts
 * per item would be a lot of DOM/SVG machinery for a handful of pixels. */
export function Sparkline({ points, width = 40, height = 16, className }: Props) {
  if (points.length < 2) return null

  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = max - min || 1
  const step = width / (points.length - 1)
  const d = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${(i * step).toFixed(1)} ${(height - ((p - min) / range) * height).toFixed(1)}`)
    .join(' ')

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} aria-hidden="true">
      <motion.path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
      />
    </svg>
  )
}
