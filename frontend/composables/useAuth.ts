export interface UserProfile {
  id: string
  email: string
  phone?: string
  full_name: string
  role: 'owner' | 'accountant' | 'manager'
  company_id?: string
}

export const useAuth = () => {
  const currentUser = useState<UserProfile | null>('currentUser', () => null)
  const authToken = useState<string | null>('authToken', () => null)
  const isAuthModalOpen = useState<boolean>('isAuthModalOpen', () => false)

  const initAuth = async () => {
    if (import.meta.client) {
      const token = localStorage.getItem('ci_radar_token')
      if (token) {
        authToken.value = token
        await fetchMe()
      }
    }
  }

  const fetchMe = async () => {
    if (!authToken.value) return null
    try {
      const data = await $fetch<any>('/api/auth/me', {
        headers: {
          Authorization: `Bearer ${authToken.value}`
        }
      })
      if (data && data.authenticated && data.user) {
        currentUser.value = data.user
        return data
      } else {
        logout()
      }
    } catch (e) {
      console.warn('Auth check failed:', e)
      logout()
    }
    return null
  }

  const setAuthSession = (token: string, user: UserProfile) => {
    authToken.value = token
    currentUser.value = user
    if (import.meta.client) {
      localStorage.setItem('ci_radar_token', token)
    }
  }

  const logout = () => {
    authToken.value = null
    currentUser.value = null
    if (import.meta.client) {
      localStorage.removeItem('ci_radar_token')
    }
  }

  const openAuthModal = () => {
    isAuthModalOpen.value = true
  }

  const closeAuthModal = () => {
    isAuthModalOpen.value = false
  }

  return {
    currentUser,
    authToken,
    isAuthModalOpen,
    initAuth,
    fetchMe,
    setAuthSession,
    logout,
    openAuthModal,
    closeAuthModal
  }
}
