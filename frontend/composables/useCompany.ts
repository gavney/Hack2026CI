export interface Company {
  id: string
  name: string
  inn: string
  balance: number
  last_balance?: number
  tax_system?: string
  director_name?: string
  industry?: string
  legal_form?: string
  ogrn?: string
  kpp?: string
  address?: string
  phone?: string
  email?: string
  has_statement?: boolean
  created_at?: string
  updated_at?: string
}

const DEFAULT_DEMO_COMPANIES: Company[] = [
  {
    id: 'C001',
    name: 'ООО «Агро-063» (Демо)',
    inn: '6164000001',
    legal_form: 'ООО',
    industry: 'Сельское хозяйство',
    balance: 1790423,
    tax_system: 'УСН «Доходы» 6%',
    director_name: 'Иванов Иван Иванович'
  },
  {
    id: 'C004',
    name: 'ООО «Донской Ритейл» (Кассовый разрыв)',
    inn: '6164000004',
    legal_form: 'ООО',
    industry: 'Розничная торговля',
    balance: 420000,
    tax_system: 'УСН «Доходы минус расходы» 15%',
    director_name: 'Ковалев Сергей Петрович'
  }
]

export const useCompany = () => {
  const companies = useState<Company[]>('companies', () => [...DEFAULT_DEMO_COMPANIES])
  const activeCompanyId = useState<string>('activeCompanyId', () => 'C001')
  const isLoading = useState<boolean>('companiesLoading', () => false)
  const isSyncing = useState<boolean>('isSyncing', () => false)

  const activeCompany = computed(() => {
    return companies.value.find(c => c.id === activeCompanyId.value) || companies.value[0] || null
  })

  const fetchCompanyDetails = async (companyId: string) => {
    try {
      const data = await $fetch<any>(`/api/companies/${companyId}`)
      if (data) {
        const bal = data.balance ?? data.last_balance ?? 0
        const idx = companies.value.findIndex(c => c.id === companyId)
        if (idx !== -1) {
          companies.value[idx] = {
            ...companies.value[idx],
            ...data,
            balance: bal
          }
        } else {
          companies.value.push({
            ...data,
            balance: bal
          })
        }
      }
    } catch (err) {
      console.warn(`Could not load details for ${companyId}:`, err)
    }
  }

  const fetchCompanies = async () => {
    try {
      isLoading.value = true
      const auth = useAuth()
      const headers: Record<string, string> = {}
      if (auth.authToken.value) {
        headers['Authorization'] = `Bearer ${auth.authToken.value}`
      }

      const data = await $fetch<Company[]>('/api/companies', { headers })
      if (Array.isArray(data) && data.length > 0) {
        companies.value = data
        if (!data.find(c => c.id === activeCompanyId.value)) {
          activeCompanyId.value = data[0].id
        }
      } else {
        // Guest mode fallback
        if (!companies.value.find(c => c.id === 'C001')) {
          companies.value = [...DEFAULT_DEMO_COMPANIES]
        }
      }

      // Fetch fresh details & balance for current company
      if (activeCompanyId.value) {
        await fetchCompanyDetails(activeCompanyId.value)
      }
    } catch (err: any) {
      console.warn('Failed to load companies, using defaults:', err)
      if (activeCompanyId.value) {
        await fetchCompanyDetails(activeCompanyId.value)
      }
    } finally {
      isLoading.value = false
    }
  }

  const setCompany = async (companyId: string) => {
    activeCompanyId.value = companyId
    if (import.meta.client) {
      localStorage.setItem('active_company_id', companyId)
    }
    await fetchCompanyDetails(companyId)
  }

  const updateBalance = async (companyId: string, newBalance: number) => {
    try {
      isSyncing.value = true
      const res = await $fetch<Company>(`/api/companies/${companyId}/balance`, {
        method: 'PATCH',
        body: { balance: newBalance }
      })
      const idx = companies.value.findIndex(c => c.id === companyId)
      if (idx !== -1 && res) {
        companies.value[idx].balance = res.balance
      }
      return res
    } catch (err: any) {
      console.error('Failed to update balance:', err)
      throw err
    } finally {
      isSyncing.value = false
    }
  }

  const updateProfile = async (companyId: string, payload: Partial<Company>) => {
    try {
      isSyncing.value = true
      const res = await $fetch<Company>(`/api/companies/${companyId}`, {
        method: 'PUT',
        body: payload
      })
      const idx = companies.value.findIndex(c => c.id === companyId)
      if (idx !== -1 && res) {
        companies.value[idx] = { ...companies.value[idx], ...res }
      }
      return res
    } catch (err: any) {
      console.error('Failed to update profile:', err)
      throw err
    } finally {
      isSyncing.value = false
    }
  }

  const createCompany = async (payload: Partial<Company>) => {
    try {
      isSyncing.value = true
      const res = await $fetch<Company>('/api/companies', {
        method: 'POST',
        body: payload
      })
      if (res) {
        companies.value.push(res)
        await setCompany(res.id)
      }
      return res
    } catch (err: any) {
      console.error('Failed to create company:', err)
      throw err
    } finally {
      isSyncing.value = false
    }
  }

  return {
    companies,
    activeCompanyId,
    activeCompany,
    isLoading,
    isSyncing,
    fetchCompanies,
    fetchCompanyDetails,
    setCompany,
    updateBalance,
    updateProfile,
    createCompany
  }
}
