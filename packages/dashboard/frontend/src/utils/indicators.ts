export const SMA_PERIODS = [10, 20, 50, 100, 200] as const
export const EMA_PERIODS = [9, 12, 20, 26, 50, 200] as const

export const SMA_COLORS: Record<number, string> = {
  10:  '#fde68a',
  20:  '#fbbf24',
  50:  '#f59e0b',
  100: '#d97706',
  200: '#b45309',
}

export const EMA_COLORS: Record<number, string> = {
  9:   '#c4b5fd',
  12:  '#a78bfa',
  20:  '#818cf8',
  26:  '#6366f1',
  50:  '#4f46e5',
  200: '#3730a3',
}

export interface OverlayConfig {
  activeSMA: number[]
  activeEMA: number[]
  bb: boolean
}
