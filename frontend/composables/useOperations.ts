export interface Operation {
  id: number
  operation_date: string
  amount: number
  direction: string
  counterparty_name?: string
  counterparty_inn?: string
  payment_purpose?: string
  category_id?: string
  category_name?: string
  confidence?: number
}

export interface StatementRecord {
  id: number | string
  filename: string
  created_at: string
  operations_count: number
  total_inflow: number
  total_outflow: number
}

export const useOperations = () => {
  const operations = useState<Operation[]>('operationsList', () => [])
  const statementHistory = useState<StatementRecord[]>('statementHistory', () => [])
  const isLoading = useState<boolean>('operationsLoading', () => false)

  const fetchOperations = async (companyId: string, limit: number = 150) => {
    if (!companyId) return []
    isLoading.value = true
    try {
      const data = await $fetch<Operation[]>(`/api/companies/${companyId}/operations`, {
        params: { limit }
      })
      operations.value = Array.isArray(data) ? data : []
      return operations.value
    } catch (err) {
      console.warn('Failed to load operations:', err)
      return []
    } finally {
      isLoading.value = false
    }
  }

  const fetchStatementHistory = async (companyId: string) => {
    if (!companyId) return []
    try {
      const data = await $fetch<StatementRecord[]>(`/api/companies/${companyId}/statements`)
      statementHistory.value = Array.isArray(data) ? data : []
      return statementHistory.value
    } catch (err) {
      console.warn('Failed to load statement history:', err)
      return []
    }
  }

  const updateCategory = async (opId: number, categoryId: string, applySimilar: boolean = false) => {
    try {
      await $fetch(`/api/operations/${opId}/category`, {
        method: 'PATCH',
        body: {
          category_id: categoryId,
          apply_to_similar: applySimilar
        }
      })
      // Update local item
      const idx = operations.value.findIndex(o => o.id === opId)
      if (idx !== -1) {
        operations.value[idx].category_id = categoryId
      }
    } catch (err) {
      console.error('Failed to update category:', err)
      throw err
    }
  }

  const uploadStatement = async (companyId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)

    const res = await $fetch<any>(`/api/companies/${companyId}/statements/upload`, {
      method: 'POST',
      body: formData
    })

    await fetchOperations(companyId)
    await fetchStatementHistory(companyId)
    return res
  }

  const rollbackStatement = async (companyId: string, statementId: string | number) => {
    await $fetch(`/api/companies/${companyId}/statements/${statementId}`, {
      method: 'DELETE'
    })
    await fetchOperations(companyId)
    await fetchStatementHistory(companyId)
  }

  return {
    operations,
    statementHistory,
    isLoading,
    fetchOperations,
    fetchStatementHistory,
    updateCategory,
    uploadStatement,
    rollbackStatement
  }
}
