import { createContext, useContext, useEffect, useState } from 'react'

/**
 * Theme for the workstation.
 *
 * Dark is the default because the instrument was designed for it, but an
 * investigator working next to a window, printing, or presenting on a
 * projector needs the light sheet. Both use the same tokens, so meaning never
 * changes with the theme: risk bands keep their order and their glyphs, and
 * colour is still never the only carrier.
 */
const ThemeContext = createContext({ theme: 'dark', toggle: () => {} })

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('abhedya-theme')
    return saved === 'light' || saved === 'dark' ? saved : 'dark'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('abhedya-theme', theme)
  }, [theme])

  const toggle = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
