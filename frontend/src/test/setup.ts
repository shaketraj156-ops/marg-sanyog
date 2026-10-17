import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest runs without globals, so Testing Library cannot register its own cleanup.
afterEach(() => {
  cleanup()
})

// Pages are loaded on demand (and bring GSAP and the charts with them), which can take a few
// seconds on a busy machine.
configure({ asyncUtilTimeout: 8000 })
