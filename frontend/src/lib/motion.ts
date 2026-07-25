import type { Transition, Variants } from 'motion/react'

/** Staggered entrance for hero/marketing content: use with `custom={i}`. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: 0.08 * i, duration: 0.45, ease: 'easeOut' } }),
}

/** Modal backdrop. */
export const overlayFade: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.18 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
}

/** Modal panel. */
export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.95, y: 8 },
  show: { opacity: 1, scale: 1, y: 0, transition: { duration: 0.18, ease: 'easeOut' } },
  exit: { opacity: 0, scale: 0.95, y: 8, transition: { duration: 0.15, ease: 'easeIn' } },
}

/** Popovers/dropdowns — faster and smaller than modals since these fire far more often. */
export const popIn: Variants = {
  hidden: { opacity: 0, scale: 0.96, y: -4 },
  show: { opacity: 1, scale: 1, y: 0, transition: { duration: 0.12, ease: 'easeOut' } },
  exit: { opacity: 0, scale: 0.96, y: -4, transition: { duration: 0.1, ease: 'easeIn' } },
}

/** Expand/collapse sections — animates the wrapping element's height. */
export const collapse: Variants = {
  hidden: { height: 0, opacity: 0 },
  show: { height: 'auto', opacity: 1, transition: { duration: 0.2, ease: 'easeInOut' } },
  exit: { height: 0, opacity: 0, transition: { duration: 0.18, ease: 'easeInOut' } },
}

/** Toast-style ephemeral notices. */
export const toastSlide: Variants = {
  hidden: { opacity: 0, y: -8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.16, ease: 'easeOut' } },
  exit: { opacity: 0, y: -8, transition: { duration: 0.14, ease: 'easeIn' } },
}

/** Subtle crossfade for swapping top-level app views. */
export const viewFade: Variants = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.15, ease: 'easeOut' } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.12, ease: 'easeIn' } },
}

/** Shared spring for `layout`/`layoutId` transitions — snappy, not bouncy. */
export const layoutSpring: Transition = { type: 'spring', stiffness: 500, damping: 40 }
