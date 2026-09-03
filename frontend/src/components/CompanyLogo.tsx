import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import clsx from 'clsx'
import { fetchLogo } from '../api'

interface Props {
  ticker: string
  size?: number
  className?: string
}

/** Renders nothing while loading and nothing on a missing/broken image —
 * this sits in the ticker header, so a placeholder box would be more
 * distracting than just not being there. */
export function CompanyLogo({ ticker, size = 36, className }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [broken, setBroken] = useState(false)

  useEffect(() => {
    setUrl(null)
    setBroken(false)
    if (!ticker) return
    let cancelled = false
    fetchLogo(ticker)
      .then(res => { if (!cancelled) setUrl(res.logo_url) })
      .catch(() => { /* no logo — fail silently, this is decorative */ })
    return () => { cancelled = true }
  }, [ticker])

  if (!url || broken) return null

  return (
    <motion.img
      key={url}
      src={url}
      alt=""
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25 }}
      onError={() => setBroken(true)}
      className={clsx('shrink-0 rounded-lg bg-white object-contain p-1 ring-1 ring-zinc-800/60 shadow-sm', className)}
      style={{ width: size, height: size }}
    />
  )
}
