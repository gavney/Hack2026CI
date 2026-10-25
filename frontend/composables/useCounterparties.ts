export interface Counterparty {
  id: number | string
  company_id: string
  name: string
  inn: string
  kpp?: string
  ogrn?: string
  role?: string // 'buyer' | 'supplier' | 'other'
  turnover?: number
  inflow_sum?: number
  outflow_sum?: number
  avg_payment_delay?: number
  delay_days?: number
  risk_level?: 'low' | 'medium' | 'high' | 'critical'
  is_blocked?: boolean
  fns_checked_at?: string
  fns_status?: string
  fns_block_count?: number
  director?: string
  address?: string
}

export const useCounterparties = () => {
  const counterparties = useState<Counterparty[]>('counterpartiesList', () => [])
  const fnsKeyStatus = useState<{ has_key: boolean; masked_key?: string }>('fnsKeyStatus', () => ({ has_key: false }))
  const isLoading = useState<boolean>('counterpartiesLoading', () => false)

  const fetchCounterparties = async (companyId: string) => {
    if (!companyId) return []
    isLoading.value = true
    try {
      const data = await $fetch<Counterparty[]>(`/api/companies/${companyId}/counterparties`)
      counterparties.value = Array.isArray(data) ? data : []
      return counterparties.value
    } catch (err) {
      console.warn('Failed to load counterparties:', err)
      return []
    } finally {
      isLoading.value = false
    }
  }

  const fetchFnsKeyStatus = async (companyId: string) => {
    if (!companyId) return
    try {
      const data = await $fetch<{ has_key: boolean; masked_key?: string }>(`/api/companies/${companyId}/counterparties/api-key-status`)
      if (data) fnsKeyStatus.value = data
    } catch (err) {
      console.warn('Failed to fetch FNS key status:', err)
    }
  }

  const toggleDelay = async (companyId: string, cpId: string | number, enabled: boolean) => {
    try {
      await $fetch(`/api/companies/${companyId}/counterparties/${cpId}/toggle-delay`, {
        method: 'PATCH',
        body: { delay_enabled: enabled }
      })
      const idx = counterparties.value.findIndex(c => c.id === cpId)
      if (idx !== -1) {
        // Toggle in local list
        counterparties.value[idx].delay_days = enabled ? 21 : 0
      }
    } catch (err) {
      console.error('Failed to toggle counterparty delay:', err)
      throw err
    }
  }

  const checkAllFns = async (companyId: string) => {
    isLoading.value = true
    try {
      const res = await $fetch(`/api/companies/${companyId}/counterparties/check-all`, {
        method: 'POST'
      })
      await fetchCounterparties(companyId)
      return res
    } catch (err) {
      console.error('Failed to check FNS:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  return {
    counterparties,
    fnsKeyStatus,
    isLoading,
    fetchCounterparties,
    fetchFnsKeyStatus,
    toggleDelay,
    checkAllFns
  }
}
