(() => {
  const storageKey = 'interviewlg_theme'
  let theme = null

  try {
    theme = window.localStorage.getItem(storageKey)
  } catch {
    // Storage can be unavailable in restricted browser modes.
  }

  if (theme !== 'light' && theme !== 'dark') {
    theme = window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  }

  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
})()
