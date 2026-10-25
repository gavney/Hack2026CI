<template>
  <div class="space-y-5">
    
    <!-- CRITICAL ALERT CALLOUT (Only shows when risk exists) -->
    <div
      v-if="hasAlertRisk"
      class="p-4 rounded-2xl bg-red-50 border border-red-200 text-red-900 card-shadow flex items-center justify-between"
    >
      <div class="flex items-center space-x-3">
        <div class="w-9 h-9 rounded-xl bg-red-500 text-white flex items-center justify-center shrink-0">
          <AlertTriangle class="w-5 h-5" />
        </div>
        <div>
          <div class="text-sm font-black">Обнаружен риск кассового разрыва!</div>
          <div class="text-xs text-red-700 mt-0.5">
            {{ currentAlert?.message || 'Деньги могут закончиться в расчетном периоде' }}
          </div>
        </div>
      </div>
      <button
        @click="$emit('switch-tab', 'breakdown')"
        class="bg-red-600 hover:bg-red-700 text-white font-bold text-xs px-3.5 py-2 rounded-xl transition shrink-0 ml-3 cursor-pointer"
      >
        Как устранить
      </button>
    </div>

    <!-- FNS RISK ALERT CALLOUT (Shows when counterparty nalogbi account blocks affect forecast) -->
    <div
      v-if="fnsDebtors.length > 0"
      class="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 card-shadow flex items-center justify-between"
    >
      <div class="flex items-center space-x-3">
        <div class="w-9 h-9 rounded-xl bg-amber-500 text-white flex items-center justify-center shrink-0">
          <ShieldAlert class="w-5 h-5" />
        </div>
        <div>
          <div class="text-sm font-black flex items-center space-x-2">
            <span>Учтен фактор риска ФНС (nalogbi)</span>
            <span class="text-[10px] bg-amber-200 text-amber-900 px-2 py-0.5 rounded-full font-bold">ст. 76 НК РФ</span>
          </div>
          <div class="text-xs text-amber-800 mt-0.5">
            В итоговом графике учтен риск: счета дебитора {{ fnsDebtors.join(', ') }} заблокированы ФНС (ст. 76 НК РФ). Поступления задержаны на 21 рабочий день.
          </div>
        </div>
      </div>
      <button
        @click="$emit('switch-tab', 'counterparties')"
        class="bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs px-3.5 py-2 rounded-xl transition shrink-0 ml-3 cursor-pointer"
      >
        Контрагенты ФНС
      </button>
    </div>

    <!-- MAIN CHART CARD -->
    <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100">
      
      <!-- Controls Bar -->
      <div class="flex items-center justify-between pb-3 border-b border-slate-100 mb-4 flex-wrap gap-2">
        <div>
          <h2 class="text-base font-extrabold text-slate-900 tracking-tight font-display">Прогноз остатка</h2>
          <p class="text-xs text-slate-400">Медианная траектория и коридор неопределенности P10–P90</p>
        </div>

        <div class="flex items-center gap-3 flex-wrap">
          <!-- Model Selector -->
          <div class="flex items-center space-x-1.5 text-xs font-bold text-slate-500">
            <span>Модель:</span>
            <div class="inline-flex bg-slate-100 p-1 rounded-xl gap-1">
              <button
                @click="changeModel('ml-ridge-lgbm')"
                :class="[
                  modelType === 'ml-ridge-lgbm' ? 'bg-emerald-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900',
                  'px-2.5 py-1 rounded-lg transition flex items-center gap-1 text-[11px] font-bold cursor-pointer'
                ]"
              >
                <span>⚡ ML-модель</span>
              </button>
              <button
                @click="changeModel('monte-carlo')"
                :class="[
                  modelType === 'monte-carlo' ? 'bg-emerald-600 text-white shadow-sm font-bold' : 'text-slate-600 hover:text-slate-900',
                  'px-2.5 py-1 rounded-lg transition flex items-center gap-1 text-[11px] cursor-pointer'
                ]"
              >
                <span>🎲 Монте-Карло</span>
              </button>
            </div>
          </div>

          <!-- Horizon Selector -->
          <div class="flex items-center space-x-1.5 text-xs font-bold text-slate-500">
            <span>Период:</span>
            <div class="inline-flex bg-slate-100 p-1 rounded-xl">
              <button
                v-for="h in [30, 60, 90]"
                :key="h"
                @click="changeHorizon(h)"
                :class="[
                  horizonDays === h ? 'bg-white text-slate-900 shadow-sm font-bold' : 'text-slate-500 hover:text-slate-900',
                  'px-3 py-1 rounded-lg transition cursor-pointer'
                ]"
              >
                {{ h }} дн
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Canvas -->
      <div class="relative w-full" style="height: 340px;">
        <ForecastChart
          :forecast-data="forecastData"
          :model-type="modelType"
          :debug-mode="debugMode"
        />
      </div>

      <!-- Legend -->
      <div class="mt-3 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between text-xs text-slate-500 gap-2">
        <div class="flex items-center space-x-4">
          <span class="inline-flex items-center space-x-1.5">
            <span class="w-3 h-0.5 bg-emerald-600"></span>
            <span class="font-semibold text-slate-700">Ожидаемый остаток</span>
          </span>
          <span class="inline-flex items-center space-x-1.5">
            <span class="w-3 h-3 rounded bg-emerald-100"></span>
            <span class="font-semibold text-slate-700">Коридор P10–P90</span>
          </span>
          <span class="inline-flex items-center space-x-1.5">
            <span class="w-3 h-0.5 bg-red-500 border-t border-dashed border-red-500"></span>
            <span class="font-semibold text-red-600">Граница разрыва (0 ₽)</span>
          </span>
          <span v-if="modelType === 'monte-carlo'" class="inline-flex items-center space-x-1.5">
            <span class="w-3 h-0.5 bg-amber-400 opacity-60" style="border-top: 1px dashed"></span>
            <span class="font-semibold text-amber-600">Симуляции MC</span>
          </span>
        </div>
        <span class="text-slate-400">Модель: <b>{{ modelLabel }}</b></span>
      </div>

    </div>

    <!-- KEY SCHEDULED EVENTS STRIP -->
    <div class="bg-white rounded-2xl p-4 card-shadow border border-slate-100">
      <div class="flex items-center justify-between flex-wrap gap-2 mb-2.5">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
          <CalendarClock class="w-3.5 h-3.5 text-ci-600" />
          <span>Ключевые события в прогнозе</span>
        </div>
        <!-- Sorting & Action buttons -->
        <div class="flex items-center space-x-1.5 overflow-x-auto text-[11px] font-bold">
          <button
            v-for="st in eventSortOptions"
            :key="st.id"
            @click="activeEventSort = st.id"
            :class="[
              activeEventSort === st.id ? 'bg-ci-600 text-white shadow-sm' : 'bg-slate-100 hover:bg-slate-200 text-slate-600',
              'px-2.5 py-1 rounded-lg transition cursor-pointer'
            ]"
          >
            {{ st.label }}
          </button>
          <button
            @click="$emit('open-event-modal', 'outflow')"
            class="bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 px-2.5 py-1 rounded-lg transition shadow-sm flex items-center space-x-1 cursor-pointer"
          >
            <Plus class="w-3 h-3" />
            <span>Событие</span>
          </button>
        </div>
      </div>

      <!-- Events list cards -->
      <div v-if="sortedEvents.length > 0" class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
        <div
          v-for="(ev, idx) in sortedEvents"
          :key="idx"
          class="p-3 rounded-xl border flex items-center justify-between transition"
          :class="ev.amount >= 0 ? 'bg-emerald-50/50 border-emerald-200/60' : 'bg-slate-50 border-slate-200/70'"
        >
          <div class="truncate mr-2">
            <div class="font-extrabold text-xs text-slate-900 truncate">
              {{ ev.description || ev.counterparty_name || 'Плановый платеж' }}
            </div>
            <div class="text-[10px] text-slate-400 mt-0.5">
              {{ formatDate(ev.event_date) }} • {{ ev.category || 'Операция' }}
            </div>
          </div>
          <div
            class="font-black text-xs whitespace-nowrap"
            :class="ev.amount >= 0 ? 'text-emerald-700' : 'text-slate-900'"
          >
            {{ ev.amount >= 0 ? '+' : '' }}{{ formatMoney(ev.amount) }} ₽
          </div>
        </div>
      </div>
      <div v-else class="text-center py-6 text-slate-400 text-xs">
        Нет запланированных платежей на выбранном горизонте.
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  AlertTriangle,
  ShieldAlert,
  CalendarClock,
  Plus
} from 'lucide-vue-next'
import ForecastChart from '~/components/charts/ForecastChart.vue'
import { formatDate, formatMoney } from '~/utils/format'

const emit = defineEmits(['switch-tab', 'open-event-modal'])

const { activeCompanyId } = useCompany()
const {
  modelType,
  horizonDays,
  forecastData,
  futureEvents,
  debugMode,
  fetchForecast
} = useForecast()
const { currentAlert } = useAlerts()

const hasAlertRisk = computed(() => {
  return currentAlert.value && (currentAlert.value.level === 'critical' || currentAlert.value.level === 'warning')
})

const fnsDebtors = computed(() => {
  const meta: any = forecastData.value?.simulation_meta || {}
  return meta.fns_affected_debtors || []
})

const modelLabel = computed(() => {
  if (modelType.value === 'monte-carlo') {
    return 'Монте-Карло (1 000 симуляций)'
  }
  return '⚡ ML-модель (Ridge + LightGBM + Platt)'
})

const activeEventSort = ref('nearest')

const eventSortOptions = [
  { id: 'nearest', label: 'Ближайшие' },
  { id: 'largest', label: 'Самые крупные' },
  { id: 'outflow', label: 'Списания (-)' },
  { id: 'inflow', label: 'Доходы (+)' }
]

const sortedEvents = computed(() => {
  let list = [...futureEvents.value]
  if (activeEventSort.value === 'largest') {
    list.sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount))
  } else if (activeEventSort.value === 'outflow') {
    list = list.filter(e => e.amount < 0)
    list.sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount))
  } else if (activeEventSort.value === 'inflow') {
    list = list.filter(e => e.amount > 0)
    list.sort((a, b) => b.amount - a.amount)
  } else {
    // nearest
    list.sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime())
  }
  return list.slice(0, 6)
})

const changeModel = async (model: 'ml-ridge-lgbm' | 'monte-carlo') => {
  modelType.value = model
  if (activeCompanyId.value) {
    await fetchForecast(activeCompanyId.value)
  }
}

const changeHorizon = async (h: number) => {
  horizonDays.value = h
  if (activeCompanyId.value) {
    await fetchForecast(activeCompanyId.value)
  }
}
</script>
