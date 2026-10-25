<template>
  <div class="space-y-4">
    <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100">
      
      <!-- Top header bar -->
      <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <div class="flex items-center space-x-2">
            <h2 class="text-lg font-black text-slate-900 font-display">Разбор кассового разрыва</h2>
            <span class="inline-flex items-center space-x-1 text-[11px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200 px-2.5 py-0.5 rounded-full">
              <Sparkles class="w-3 h-3 text-emerald-600" />
              <span>GigaChat AI</span>
            </span>
          </div>
          <p class="text-xs text-slate-400">Экономическая причина и 3 персональных шага предотвращения разрыва с помощью GigaChat</p>
        </div>
        <div class="flex items-center space-x-2">
          <button
            @click="handleRefreshGigaChat"
            :disabled="isBreakdownLoading"
            class="text-xs font-bold bg-emerald-50 hover:bg-emerald-100 disabled:opacity-50 text-emerald-800 border border-emerald-200 px-3 py-1.5 rounded-xl transition flex items-center space-x-1.5 shadow-2xs cursor-pointer"
          >
            <RefreshCw class="w-3.5 h-3.5 text-emerald-600" :class="{ 'animate-spin': isBreakdownLoading }" />
            <span>{{ isBreakdownLoading ? 'GigaChat думает...' : 'Пересчитать через GigaChat' }}</span>
          </button>
          <span
            class="px-3 py-1 rounded-full font-bold text-xs uppercase"
            :class="hasAlertRisk ? 'bg-red-100 text-red-900' : 'bg-emerald-100 text-emerald-900'"
          >
            {{ hasAlertRisk ? 'Критический' : 'В норме' }}
          </span>
        </div>
      </div>

      <!-- Spinner while GigaChat is analyzing -->
      <div
        v-if="isBreakdownLoading"
        class="flex flex-col items-center justify-center p-12 bg-white rounded-2xl border border-slate-200 card-shadow my-4 text-center"
      >
        <div class="relative flex items-center justify-center mb-4">
          <div class="w-12 h-12 border-4 border-emerald-100 border-t-emerald-600 rounded-full animate-spin"></div>
          <Sparkles class="w-5 h-5 text-emerald-600 absolute" />
        </div>
        <div class="text-sm font-black text-slate-800">GigaChat анализирует структуру кассового разрыва...</div>
        <div class="text-xs text-slate-500 mt-1 max-w-md">
          Языковая модель оценивает выдержку денежных потоков до и после даты разрыва, формулирует причину и подбирает 3 операционных шага
        </div>
      </div>

      <!-- Breakdown Content Area -->
      <div v-else class="space-y-5">
        <div class="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
          <div class="flex items-center justify-between pb-2 border-b border-slate-200">
            <div class="text-sm font-black text-slate-900">Кассовый разрыв</div>
            <span
              class="text-xs font-black px-2 py-0.5 rounded-full"
              :class="hasAlertRisk ? 'text-red-700 bg-red-100' : 'text-emerald-700 bg-emerald-100'"
            >
              {{ hasAlertRisk ? 'Требуется внимание' : 'Ликвидность обеспечена' }}
            </span>
          </div>
          
          <!-- Key Metrics Grid -->
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
            <!-- 1. Critical Deficit -->
            <div class="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs">
              <span class="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Критический дефицит</span>
              <div class="text-base font-black text-red-600 font-display">
                {{ formatMoney(criticalDeficit) }} ₽
              </div>
            </div>

            <!-- 2. Gap Date -->
            <div class="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs">
              <span class="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Дата просадки</span>
              <div class="text-sm font-bold text-slate-900">
                {{ formatDate(gapDate) }}
              </div>
            </div>

            <!-- 3. Duration -->
            <div class="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs">
              <span class="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Длительность</span>
              <div class="text-xs font-bold text-slate-900 leading-snug break-words">
                {{ durationText }}
              </div>
            </div>

            <!-- 4. GigaChat Reason -->
            <div class="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs">
              <span class="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Причина (GigaChat)</span>
              <div class="text-xs font-bold text-slate-800 leading-snug break-words">
                {{ currentAlert?.ai_reason || 'Анализ факторов дефицита ликвидности' }}
              </div>
            </div>
          </div>

          <!-- Detailed GigaChat Explanation -->
          <div class="pt-1">
            <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-1 flex items-center space-x-1">
              <Bot class="w-3.5 h-3.5 text-emerald-600" />
              <span>Аналитическое заключение GigaChat:</span>
            </div>
            <p class="text-xs text-slate-700 leading-relaxed font-medium bg-white p-3 rounded-xl border border-slate-100">
              {{ currentAlert?.ai_summary || currentAlert?.message || 'Расчет выполнен по прогнозной модели на основе выписки.' }}
            </p>
          </div>
        </div>

        <!-- 3 Step Actions -->
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center space-x-1.5">
            <CheckCircle2 class="w-4 h-4 text-emerald-600" />
            <span>3 шага для предотвращения разрыва</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div
              v-for="(act, idx) in mitigationActions"
              :key="idx"
              class="p-4 bg-white rounded-2xl border border-slate-200 card-shadow flex flex-col justify-between space-y-3 transition hover:border-emerald-500/50"
            >
              <div class="space-y-1.5">
                <div class="flex items-center justify-between">
                  <span class="text-[10px] font-black uppercase text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-lg border border-emerald-100">
                    Шаг {{ idx + 1 }}
                  </span>
                  <span class="font-black text-xs text-emerald-700">
                    +{{ formatMoney(act.estimated_effect) }} ₽
                  </span>
                </div>
                <div class="font-extrabold text-sm text-slate-900 leading-tight">
                  {{ act.title }}
                </div>
                <p class="text-xs text-slate-500 leading-relaxed">
                  {{ act.description }}
                </p>
              </div>

              <button
                @click="handleApplyAction(idx)"
                :disabled="isApplying"
                class="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-xs py-2 rounded-xl transition shadow-sm flex items-center justify-center space-x-1.5 cursor-pointer"
              >
                <Check class="w-3.5 h-3.5" />
                <span>Применить</span>
              </button>
            </div>
          </div>
        </div>

      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Sparkles,
  RefreshCw,
  Bot,
  CheckCircle2,
  Check
} from 'lucide-vue-next'
import { formatDate, formatMoney } from '~/utils/format'
import type { MitigationAction } from '~/composables/useAlerts'

const emit = defineEmits(['switch-tab'])

const { activeCompanyId } = useCompany()
const { forecastData, horizonDays, modelType, fetchForecast } = useForecast()
const { currentAlert, isBreakdownLoading, refreshAIBreakdown, applyPreventionAction } = useAlerts()
const { showToast } = useToast()

const isApplying = ref(false)

const hasAlertRisk = computed(() => {
  return currentAlert.value && (currentAlert.value.level === 'critical' || currentAlert.value.level === 'warning')
})

const criticalDeficit = computed(() => {
  if (currentAlert.value?.shortfall_p50) return currentAlert.value.shortfall_p50
  if (currentAlert.value?.gap_amount) return currentAlert.value.gap_amount
  if (forecastData.value?.min_balance && forecastData.value.min_balance < 0) {
    return Math.abs(forecastData.value.min_balance)
  }
  return 320000
})

const gapDate = computed(() => {
  return currentAlert.value?.gap_date || forecastData.value?.first_gap_date || '2026-10-25'
})

const durationText = computed(() => {
  return `Не выходит из дефицита до конца горизонта (${horizonDays.value} дн., с ${formatDate(gapDate.value)})`
})

const defaultActions: MitigationAction[] = [
  {
    action_type: 'delay_payment',
    title: 'Отсрочка платежа поставщику',
    description: 'Согласовать перенос оплаты регулярному поставщику на 14 дней без штрафных санкций.',
    estimated_effect: 350000
  },
  {
    action_type: 'request_prepayment',
    title: 'Досрочная оплата от дебитора',
    description: 'Предложить скидку 2% ключевому покупателю за ускорение оплаты задолженности до даты разрыва.',
    estimated_effect: 420000
  },
  {
    action_type: 'cost_reduction',
    title: 'Оптимизация некритичных расходов',
    description: 'Временно заморозить маркетинговые и представительские расходы до восстановления планового остатка.',
    estimated_effect: 180000
  }
]

const mitigationActions = computed(() => {
  if (currentAlert.value?.actions && currentAlert.value.actions.length > 0) {
    return currentAlert.value.actions
  }
  return defaultActions
})

const handleRefreshGigaChat = async () => {
  if (!activeCompanyId.value) return
  await refreshAIBreakdown(activeCompanyId.value, horizonDays.value, modelType.value)
  showToast('Разбор успешно сформирован языковой моделью GigaChat!', 'success')
}

const handleApplyAction = async (idx: number) => {
  if (!activeCompanyId.value) return
  isApplying.value = true
  try {
    const res = await applyPreventionAction(activeCompanyId.value, idx, gapDate.value)
    showToast(res.toastMsg, 'success')
    await fetchForecast(activeCompanyId.value)
    emit('switch-tab', 'radar')
  } catch (err: any) {
    showToast(err.message || 'Ошибка применения действия', 'error')
  } finally {
    isApplying.value = false
  }
}
</script>
