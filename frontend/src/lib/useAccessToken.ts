import { useAuth } from '@clerk/react'
import { useCallback } from 'react'

export function useAccessToken(): () => Promise<string> {
  const { getToken } = useAuth()

  return useCallback(async () => {
    const token = await getToken()
    if (!token) {
      throw new Error('Your session has expired. Please sign in again.')
    }
    return token
  }, [getToken])
}
