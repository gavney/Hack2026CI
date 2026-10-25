export interface MitigationAction {
  id?: string
  action_type: 'delay_payment' | 'request_prepayment' | 'cost_reduction' | string
  title: string
  description: string
  estimated_effect: number
  timeline_days?: number
}

export interface AlertData {
  id?: string
  company_id: string
  level: 'ok' | 'info' | 'warning' | 'critical'
  gap_date?: string | null
  gap_amount?: number | null
  shortfall_p10?: number | null
  shortfall_p50?: number | null
  duration_days?: number
  duration_text?: string
  main_factor?: string
  probability?: number
  reason?: string
  message: string
  ai_reason?: string | null
  ai_summary?: string | null
  actions?: MitigationAction[]
  created_at?: string
}

export const useAlerts = () => {
  const currentAlert = useState<AlertData | null>('currentAlert', () => null)
  const isBreakdownLoading = useState<boolean>('isBreakdownLoading', () => false)

  const normalizeAlert = (raw: any): AlertData | null => {
    if (!raw) return null
    return {
      ...raw,
      message: raw.reason || raw.message || 'Кассовое состояние в норме'
    }
  }

  const fetchAlerts = async (companyId: string) => {
    if (!companyId) return null
    try {
      const data = await $fetch<any>(`/api/companies/${companyId}/alerts`)
      if (Array.isArray(data)) {
        currentAlert.value = normalizeAlert(data[0])
      } else {
        currentAlert.value = normalizeAlert(data)
      }
      return currentAlert.value
    } catch (err) {
      console.warn('Failed to load alerts:', err)
      return null
    }
  }

  const refreshAIBreakdown = async (companyId: string, horizon: number = 30, model: string = 'ml-ridge-lgbm') => {
    if (!companyId) return
    isBreakdownLoading.value = true
    try {
      await $fetch(`/api/companies/${companyId}/ai-breakdown`, {
        method: 'POST',
        params: {
          horizon,
          model
        }
      })
      await fetchAlerts(companyId)
    } catch (err) {
      console.error('Failed to refresh AI breakdown:', err)
      await fetchAlerts(companyId)
    } finally {
      isBreakdownLoading.value = false
    }
  }

  const applyPreventionAction = async (companyId: string, actionIdx: number, gapDateStr?: string | null) => {
    const alertData = currentAlert.value
    if (!alertData || !alertData.actions || !alertData.actions[actionIdx]) {
      throw new Error('Действие не найдено')
    }

    const act = alertData.actions[actionIdx]
    const effect = Math.abs(act.estimated_effect || 300000.0)

    // Calculate target date: 1 day before gap date or tomorrow
    let targetDate = new Date()
    if (gapDateStr) {
      const parts = gapDateStr.split('-')
      if (parts.length === 3) {
        targetDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]))
        targetDate.setDate(targetDate.getDate() - 1)
      }
    } else {
      targetDate.setDate(targetDate.getDate() + 1)
    }
    const now = new Date()
    if (targetDate <= now) {
      targetDate = new Date()
      targetDate.setDate(targetDate.getDate() + 1)
    }
    const eventDateStr = targetDate.toISOString().split('T')[0]

    let counterparty = 'Оптимизация некритичных расходов бизнеса'
    let categoryId = 'cat_other'
    let toastMsg = `Оптимизация расходов выполнена! В график добавлено +${effect.toLocaleString('ru-RU')} ₽`

    if (act.action_type === 'delay_payment') {
      counterparty = 'Отсрочка платежа поставщику (согласовано +14 дн)'
      categoryId = 'cat_procurement'
      toastMsg = `Отсрочка согласована! В график добавлено +${effect.toLocaleString('ru-RU')} ₽`
    } else if (act.action_type === 'request_prepayment') {
      counterparty = 'Досрочная оплата от дебитора (со скидкой)'
      categoryId = 'cat_revenue_client'
      toastMsg = `Досрочная оплата согласована! В график добавлено +${effect.toLocaleString('ru-RU')} ₽`
    }

    await $fetch(`/api/companies/${companyId}/events`, {
      method: 'POST',
      body: {
        event_date: eventDateStr,
        amount: effect,
        probability: 1.0,
        category_id: categoryId,
        counterparty_name: counterparty,
        counterparty_inn: '7707083893',
        note: act.title
      }
    })

    return { toastMsg, effect, eventDateStr }
  }

  return {
    currentAlert,
    isBreakdownLoading,
    fetchAlerts,
    refreshAIBreakdown,
    applyPreventionAction
  }
}
