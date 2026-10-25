export interface ScenarioComparisonPoint {
  date: string
  baseline_p50: number
  scenario_p50: number
  difference: number
}

export interface ScenarioComparisonResult {
  comparison: ScenarioComparisonPoint[]
  baseline_end_balance: number
  scenario_end_balance: number
  scenario_min_balance: number
  scenario_first_gap?: string | null
  scenario_shortfall?: number | null
}

export const useScenarios = () => {
  const activeScenarioId = useState<string>('activeScenarioId', () => 'delay')
  const scenarioHorizon = useState<number>('scenarioHorizon', () => 30)
  const comparisonData = useState<ScenarioComparisonResult | null>('scenarioComparisonData', () => null)
  const isLoading = useState<boolean>('scenarioLoading', () => false)

  const scenarioParams = useState('scenarioParams', () => ({
    delay_days: 14,
    drop_percent: 20,
    amount: 250000,
    increase_percent: 15,
    expense_days_ahead: 5
  }))

  const fetchComparison = async (companyId: string) => {
    if (!companyId) return
    isLoading.value = true
    try {
      const cleanId = activeScenarioId.value.replace(`_${companyId}`, '')
      let params: Record<string, any> = {
        horizon: scenarioHorizon.value
      }

      if (cleanId.includes('delay')) {
        params.delay_days = scenarioParams.value.delay_days
      } else if (cleanId.includes('drop')) {
        params.drop_percent = scenarioParams.value.drop_percent
      } else if (cleanId.includes('expense')) {
        params.amount = scenarioParams.value.amount
        params.expense_days_ahead = scenarioParams.value.expense_days_ahead
      } else if (cleanId.includes('cost')) {
        params.increase_percent = scenarioParams.value.increase_percent
      }

      const data = await $fetch<ScenarioComparisonResult>(`/api/companies/${companyId}/scenarios/${cleanId}/compare`, {
        params
      })
      comparisonData.value = data
      return data
    } catch (err) {
      console.warn('Failed to load scenario comparison:', err)
      return null
    } finally {
      isLoading.value = false
    }
  }

  const setScenario = (scenId: string) => {
    activeScenarioId.value = scenId
  }

  return {
    activeScenarioId,
    scenarioHorizon,
    scenarioParams,
    comparisonData,
    isLoading,
    setScenario,
    fetchComparison
  }
}
