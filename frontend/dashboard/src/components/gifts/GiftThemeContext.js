// ═══════════════════════════════════════════════════════════════
// GiftFlow — theme access
//
// The dashboard's ThemeContext lives inside the BiotactDashboard
// monolith and is not exported. To keep GiftFlow fully decoupled
// (no circular import into the 2700-line monolith), GiftFlowPage
// receives { theme, isDark } as props and re-publishes them through
// this lightweight context so nested components can read them.
// ═══════════════════════════════════════════════════════════════

import { createContext, useContext } from 'react';

export const GiftThemeContext = createContext(null);

export function useGiftTheme() {
  const value = useContext(GiftThemeContext);
  if (!value) {
    throw new Error('useGiftTheme must be used within <GiftThemeContext.Provider>');
  }
  return value;
}
