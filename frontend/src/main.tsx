import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import './index.css'
import App from './App'
import { ThemeProvider } from './contexts/ThemeContext'
import { PrefsProvider } from './contexts/PrefsContext'
import { AuthProvider } from './contexts/AuthContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
      <PrefsProvider>
        <ThemeProvider>
        <MotionConfig reducedMotion="user">
          <App />
        </MotionConfig>
      </ThemeProvider>
      </PrefsProvider>
    </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
