/** @type {import('tailwindcss').Config} */

// ── Stakeout design tokens ────────────────────────────────────────────────
// The existing components are written against Tailwind's `zinc` (neutrals)
// and `indigo` (accent) scales. Rather than rewriting hundreds of class
// names, we REMAP those two scales to the Stakeout palette:
//   zinc   → "ink": deep blue-black neutrals (terminal at night)
//   indigo → "brass": the opening-bell gold that anchors the brand
// Semantic up/down colors (emerald / red) are left untouched.

const ink = {
  50:  '#F4F6FA',
  100: '#EDF0F5',
  200: '#D6DCE6',
  300: '#B9C2D1',
  400: '#97A3B8',
  500: '#76839B',
  600: '#55627A',
  700: '#2A3446',
  800: '#1C2432',
  900: '#10161F',
  950: '#0A0E16',
}

const brass = {
  50:  '#FBF6E9',
  100: '#F6EBCB',
  200: '#F0DCA4',
  300: '#EDCB80',
  400: '#E4B95B',
  500: '#D9A93F',
  600: '#B8860B',
  700: '#96690A',
  800: '#6E4D08',
  900: '#4A3305',
  950: '#2A2008',
}

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        zinc: ink,
        indigo: brass,
        ink,
        brass,
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Space Grotesk', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'JetBrains Mono', 'Consolas', 'monospace'],
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        marquee: {
          from: { transform: 'translateX(0)' },
          to: { transform: 'translateX(-50%)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.45s ease-out both',
        marquee: 'marquee 45s linear infinite',
      },
    },
  },
  plugins: [],
}
