export interface ToastItem {
  id: string
  message: string
  type: 'success' | 'error' | 'info' | 'warning'
}

export const useToast = () => {
  const toasts = useState<ToastItem[]>('toasts', () => [])

  const showToast = (message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info', duration: number = 4000) => {
    const id = Math.random().toString(36).substring(2, 9)
    toasts.value.push({ id, message, type })

    setTimeout(() => {
      removeToast(id)
    }, duration)
  }

  const removeToast = (id: string) => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  return {
    toasts,
    showToast,
    removeToast
  }
}
