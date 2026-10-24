const params = new URLSearchParams(window.location.search)
const path = window.location.pathname.replace(/\/+$/, '')
const isDev = import.meta.env.DEV

export const demoMode =
  isDev &&
  (import.meta.env.VITE_DEMO_MODE === 'true' ||
    params.has('demo') ||
    path.endsWith('/demo'))

export const landingMode =
  isDev && (params.has('landing') || path.endsWith('/landing'))
