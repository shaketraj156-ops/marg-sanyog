// Tokens live in memory and are mirrored to sessionStorage, so a page reload keeps the session
// but closing the tab ends it. Nothing is written to localStorage.

const ACCESS_KEY = 'bp.access'
const REFRESH_KEY = 'bp.refresh'

export interface TokenStore {
  getAccess(): string | null
  getRefresh(): string | null
  set(access: string, refresh: string): void
  clear(): void
}

export function createTokenStore(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>): TokenStore {
  let access: string | null = storage.getItem(ACCESS_KEY)
  let refresh: string | null = storage.getItem(REFRESH_KEY)
  return {
    getAccess: () => access,
    getRefresh: () => refresh,
    set(newAccess, newRefresh) {
      access = newAccess
      refresh = newRefresh
      storage.setItem(ACCESS_KEY, newAccess)
      storage.setItem(REFRESH_KEY, newRefresh)
    },
    clear() {
      access = null
      refresh = null
      storage.removeItem(ACCESS_KEY)
      storage.removeItem(REFRESH_KEY)
    },
  }
}
