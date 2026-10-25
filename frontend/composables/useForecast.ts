export interface ForecastResponse {
  dates: string[]
  p10: number[]
  p50: number[]
  p90: number[]
  min_balance: number
  has_risk: boolean
  first_gap_date: string | null
  first_gap_amount: number | null
  max_gap_amount?: number | null
  risk_probability: number
  risk_score?: number
  model_version?: string
  simulation_meta?: {
    iterations?: number
    execution_time_ms?: number
    var_95?: number
    cvar_95?: number
  }
  simulations?: {
    p5: number[]
    p25: number[]
    p50: number[]
    p75: number[]
    p95: number[]
    samples?: number[][]
  }
  contributions?: Array<{
    category: string
    amount: number
    percent: number
  }>
}

export interface PlannedEvent {
  id?: string | number
  event_date: string
  amount: number
  description: string
  counterparty_name?: string
  counterparty_inn?: string
  probability?: number
  category?: string
  created_at?: string
}

export const useForecast = () => {
  const modelType = useState<'ml-ridge-lgbm' | 'monte-carlo'>('forecastModelType', () => 'ml-ridge-lgbm')
  const horizonDays = useState<number>('forecastHorizonDays', () => 30)
  const forecastData = useState<ForecastResponse | null>('forecastData', () => null)
  const futureEvents = useState<PlannedEvent[]>('futureEvents', () => [])
  const isLoading = useState<boolean>('forecastLoading', () => false)
  const debugMode = useState<boolean>('forecastDebugMode', () => false)

  const fetchForecast = async (companyId: string) => {
    if (!companyId) return
    try {
      isLoading.value = true
      const data = await $fetch<ForecastResponse>(`/api/companies/${companyId}/forecast`, {
        params: {
          horizon: horizonDays.value,
          model: modelType.value
        }
      })
      forecastData.value = data
      return data
    } catch (err) {
      console.error('Failed to load forecast:', err)
    } finally {
      isLoading.value = false
    }
  }

  const fetchEvents = async (companyId: string) => {
    if (!companyId) return []
    try {
      const data = await $fetch<PlannedEvent[]>(`/api/companies/${companyId}/events`)
      futureEvents.value = Array.isArray(data) ? data : []
      return futureEvents.value
    } catch (err) {
      console.warn('Failed to load events:', err)
      return []
    }
  }

  const addEvent = async (companyId: string, payload: PlannedEvent) => {
    try {
      const res = await $fetch<PlannedEvent>(`/api/companies/${companyId}/events`, {
        method: 'POST',
        body: payload
      })
      await fetchEvents(companyId)
      await fetchForecast(companyId)
      return res
    } catch (err) {
      console.error('Failed to add event:', err)
      throw err
    }
  }

  const deleteEvent = async (companyId: string, eventId: string | number) => {
    try {
      await $fetch(`/api/companies/${companyId}/events/${eventId}`, {
        method: 'DELETE'
      })
      await fetchEvents(companyId)
      await fetchForecast(companyId)
    } catch (err) {
      console.error('Failed to delete event:', err)
      throw err
    }
  }

  return {
    modelType,
    horizonDays,
    forecastData,
    futureEvents,
    isLoading,
    debugMode,
    fetchForecast,
    fetchEvents,
    addEvent,
    deleteEvent
  }
}
