<template>
  <div class="space-y-4">
    <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100">
      
      <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h2 class="text-lg font-black text-slate-900 font-display">Стресс-сценарии «Что если»</h2>
          <p class="text-xs text-slate-400">Сравнение базового прогноза со стресс-ситуацией на одном графике</p>
        </div>
        <div class="flex items-center space-x-2">
          <!-- Horizon pills -->
          <div class="flex bg-slate-100 p-1 rounded-xl text-[11px] font-bold">
            <button
              v-for="d in [14, 30, 60, 90]"
              :key="d"
              @click="changeHorizon(d)"
              :class="[
                scenarioHorizon === d ? 'bg-white text-emerald-800 shadow-xs font-black' : 'text-slate-600 hover:text-slate-900',
                'px-2.5 py-1 rounded-lg transition cursor-pointer'
              ]"
            >
              {{ d }} дн
            </button>
          </div>
          <!-- Custom scenario button -->
          <button
            @click="$emit('open-custom-scenario')"
            class="flex items-center space-x-1 px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-bold text-xs rounded-xl border border-emerald-200 transition cursor-pointer"
          >
            <Plus class="w-3.5 h-3.5" />
            <span>Свой сценарий</span>
          </button>
        </div>
      </div>

      <!-- Preset Scenario Cards -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <!-- 1. Delay -->
        <button
          @click="selectPreset('delay')"
          :class="[
            activeScenarioId === 'delay' ? 'border-2 border-ci-600 bg-emerald-50/80 shadow-xs' : 'border border-slate-200 bg-white hover:border-slate-300',
            'p-3 rounded-xl text-left transition cursor-pointer'
          ]"
        >
          <div class="text-[10px] font-bold" :class="activeScenarioId === 'delay' ? 'text-ci-800' : 'text-slate-400'">
            Клиент задержит
          </div>
          <div class="font-extrabold text-xs text-slate-900 mt-0.5">
            +{{ scenarioParams.delay_days }} дней
          </div>
        </button>

        <!-- 2. Revenue Drop -->
        <button
          @click="selectPreset('drop')"
          :class="[
            activeScenarioId === 'drop' ? 'border-2 border-ci-600 bg-emerald-50/80 shadow-xs' : 'border border-slate-200 bg-white hover:border-slate-300',
            'p-3 rounded-xl text-left transition cursor-pointer'
          ]"
        >
          <div class="text-[10px] font-bold" :class="activeScenarioId === 'drop' ? 'text-ci-800' : 'text-slate-400'">
            Спад выручки
          </div>
          <div class="font-extrabold text-xs text-slate-900 mt-0.5">
            -{{ scenarioParams.drop_percent }}% продаж
          </div>
        </button>

        <!-- 3. Unexpected Expense -->
        <button
          @click="selectPreset('expense')"
          :class="[
            activeScenarioId === 'expense' ? 'border-2 border-ci-600 bg-emerald-50/80 shadow-xs' : 'border border-slate-200 bg-white hover:border-slate-300',
            'p-3 rounded-xl text-left transition cursor-pointer'
          ]"
        >
          <div class="text-[10px] font-bold" :class="activeScenarioId === 'expense' ? 'text-ci-800' : 'text-slate-400'">
            Внеплановый расход
          </div>
          <div class="font-extrabold text-xs text-slate-900 mt-0.5">
            -{{ formatMoney(scenarioParams.amount) }} ₽
          </div>
        </button>

        <!-- 4. Cost Hike -->
        <button
          @click="selectPreset('cost')"
          :class="[
            activeScenarioId === 'cost' ? 'border-2 border-ci-600 bg-emerald-50/80 shadow-xs' : 'border border-slate-200 bg-white hover:border-slate-300',
            'p-3 rounded-xl text-left transition cursor-pointer'
          ]"
        >
          <div class="text-[10px] font-bold" :class="activeScenarioId === 'cost' ? 'text-ci-800' : 'text-slate-400'">
            Рост расходов
          </div>
          <div class="font-extrabold text-xs text-slate-900 mt-0.5">
            +{{ scenarioParams.increase_percent }}% затрат
          </div>
        </button>
      </div>

      <!-- Interactive Scenario Parameter Editor -->
      <div class="p-4 bg-slate-50 border border-slate-200 rounded-2xl mb-4 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <div class="w-6 h-6 rounded-lg bg-ci-100 text-ci-800 flex items-center justify-center">
              <Sliders class="w-3.5 h-3.5" />
            </div>
            <span class="text-xs font-black text-slate-800">
              Параметры стресс-модели: <span class="text-ci-700">{{ activeScenarioTitle }}</span>
            </span>
          </div>
          <button
            @click="cancelScenario"
            class="text-[11px] font-bold text-slate-600 hover:text-red-700 bg-white px-2.5 py-1 rounded-lg border border-slate-200 shadow-2xs hover:bg-red-50 hover:border-red-200 transition flex items-center space-x-1 cursor-pointer"
          >
            <XCircle class="w-3.5 h-3.5 text-slate-400" />
            <span>Сбросить к норме</span>
          </button>
        </div>

        <!-- Controls depending on active scenario -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <!-- Delay controls -->
          <div v-if="activeScenarioId === 'delay'" class="space-y-1.5">
            <div class="flex justify-between items-center font-bold text-slate-700">
              <span>Срок задержки оплаты:</span>
              <span class="text-ci-700 font-black bg-emerald-50 px-2 py-0.5 rounded-lg border border-emerald-200">
                +{{ scenarioParams.delay_days }} дней
              </span>
            </div>
            <input
              type="range"
              min="3"
              max="60"
              step="1"
              v-model.number="scenarioParams.delay_days"
              @input="onParamChange"
              class="w-full accent-ci-600 cursor-pointer"
            >
            <div class="flex items-center space-x-1.5 pt-1">
              <span class="text-[10px] text-slate-400 font-bold">Быстрый выбор:</span>
              <button
                v-for="val in [7, 14, 21, 30, 45]"
                :key="val"
                @click="scenarioParams.delay_days = val; onParamChange()"
                class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-emerald-500 transition cursor-pointer"
              >
                +{{ val }} дн
              </button>
            </div>
          </div>

          <!-- Revenue Drop controls -->
          <div v-else-if="activeScenarioId === 'drop'" class="space-y-1.5">
            <div class="flex justify-between items-center font-bold text-slate-700">
              <span>Снижение входящих оплат:</span>
              <span class="text-amber-700 font-black bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-200">
                -{{ scenarioParams.drop_percent }}%
              </span>
            </div>
            <input
              type="range"
              min="5"
              max="60"
              step="5"
              v-model.number="scenarioParams.drop_percent"
              @input="onParamChange"
              class="w-full accent-amber-600 cursor-pointer"
            >
            <div class="flex items-center space-x-1.5 pt-1">
              <span class="text-[10px] text-slate-400 font-bold">Быстрый выбор:</span>
              <button
                v-for="val in [10, 20, 30, 40, 50]"
                :key="val"
                @click="scenarioParams.drop_percent = val; onParamChange()"
                class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-amber-500 transition cursor-pointer"
              >
                -{{ val }}%
              </button>
            </div>
          </div>

          <!-- Expense controls -->
          <div v-else-if="activeScenarioId === 'expense'" class="space-y-1.5">
            <div class="flex justify-between items-center font-bold text-slate-700">
              <span>Сумма внезапного платежа:</span>
              <span class="text-slate-900 font-black bg-slate-100 px-2 py-0.5 rounded-lg border border-slate-200">
                {{ formatMoney(scenarioParams.amount) }} ₽
              </span>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <input
                type="number"
                step="25000"
                min="25000"
                v-model.number="scenarioParams.amount"
                @input="onParamChange"
                class="w-full bg-white border border-slate-200 rounded-xl p-2 font-black text-sm text-slate-900 focus:ring-2 focus:ring-ci-500"
              >
              <select
                v-model.number="scenarioParams.expense_days_ahead"
                @change="onParamChange"
                class="w-full bg-white border border-slate-200 rounded-xl p-2 font-bold text-xs text-slate-800"
              >
                <option :value="3">Через 3 дня</option>
                <option :value="5">Через 5 дней</option>
                <option :value="10">Через 10 дней</option>
                <option :value="15">Через 15 дней</option>
                <option :value="25">Через 25 дней</option>
              </select>
            </div>
          </div>

          <!-- Cost Hike controls -->
          <div v-else class="space-y-1.5">
            <div class="flex justify-between items-center font-bold text-slate-700">
              <span>Увеличение постоянных трат:</span>
              <span class="text-amber-700 font-black bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-200">
                +{{ scenarioParams.increase_percent }}%
              </span>
            </div>
            <input
              type="range"
              min="5"
              max="50"
              step="5"
              v-model.number="scenarioParams.increase_percent"
              @input="onParamChange"
              class="w-full accent-amber-600 cursor-pointer"
            >
            <div class="flex items-center space-x-1.5 pt-1">
              <span class="text-[10px] text-slate-400 font-bold">Быстрый выбор:</span>
              <button
                v-for="val in [10, 15, 25, 40]"
                :key="val"
                @click="scenarioParams.increase_percent = val; onParamChange()"
                class="px-2 py-0.5 bg-white border border-slate-200 rounded-md text-[10px] font-bold text-slate-700 hover:border-amber-500 transition cursor-pointer"
              >
                +{{ val }}%
              </button>
            </div>
          </div>

          <!-- Explanation box -->
          <div class="p-2.5 bg-white rounded-xl border border-slate-200 text-slate-600 text-[11px] leading-relaxed flex flex-col justify-center">
            <div class="font-bold text-slate-800 mb-0.5 flex items-center space-x-1">
              <Info class="w-3.5 h-3.5 text-ci-600" />
              <span>Механизм стресс-теста</span>
            </div>
            <span>{{ scenarioMechanismText }}</span>
          </div>
        </div>
      </div>

      <!-- Chart -->
      <div class="relative w-full" style="height: 310px;">
        <ScenarioChart :points="comparisonData?.comparison || []" />
      </div>

      <!-- 4 Delta Metrics -->
      <div class="mt-4 pt-3 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div class="p-3 bg-slate-50 rounded-2xl border border-slate-100">
          <div class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Базовый итог</div>
          <div class="text-sm font-black text-slate-900 mt-1">
            {{ formatMoney(comparisonData?.baseline_end_balance) }} ₽
          </div>
          <div class="text-[10px] text-slate-400 mt-0.5">через {{ scenarioHorizon }} дней</div>
        </div>
        <div
          class="p-3 rounded-2xl border"
          :class="hasScenarioGap ? 'bg-red-50/70 border-red-200' : 'bg-emerald-50/70 border-emerald-200'"
        >
          <div class="text-[10px] font-bold uppercase tracking-wider" :class="hasScenarioGap ? 'text-red-700' : 'text-emerald-700'">
            Итог сценария
          </div>
          <div class="text-sm font-black mt-1" :class="hasScenarioGap ? 'text-red-700' : 'text-emerald-800'">
            {{ formatMoney(comparisonData?.scenario_end_balance) }} ₽
          </div>
          <div class="text-[10px] mt-0.5" :class="hasScenarioGap ? 'text-red-500' : 'text-emerald-600'">
            со стресс-фактором
          </div>
        </div>
        <div class="p-3 bg-slate-50 rounded-2xl border border-slate-100">
          <div class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Стресс-дельта</div>
          <div class="text-sm font-black mt-1" :class="stressDelta < 0 ? 'text-red-600' : 'text-emerald-600'">
            {{ stressDelta > 0 ? '+' : '' }}{{ formatMoney(stressDelta) }} ₽
          </div>
          <div class="text-[10px] text-slate-400 mt-0.5">чистый удар по кассе</div>
        </div>
        <div
          class="p-3 rounded-2xl border"
          :class="hasScenarioGap ? 'bg-red-100 text-red-950 border-red-300' : 'bg-emerald-50 border-emerald-200'"
        >
          <div class="text-[10px] font-bold uppercase tracking-wider" :class="hasScenarioGap ? 'text-red-800' : 'text-emerald-700'">
            Кассовый разрыв
          </div>
          <div class="text-sm font-black mt-1" :class="hasScenarioGap ? 'text-red-800' : 'text-emerald-800'">
            {{ hasScenarioGap ? 'Разрыв: ' + formatMoney(minScenarioBalance) + ' ₽' : 'Мин: ' + formatMoney(minScenarioBalance) + ' ₽' }}
          </div>
          <div class="text-[10px] mt-0.5" :class="hasScenarioGap ? 'text-red-700 font-bold' : 'text-emerald-600'">
            {{ hasScenarioGap ? 'в расчетном периоде' : 'стабильный запас' }}
          </div>
        </div>
      </div>

      <!-- Action Recommendation Box -->
      <div
        class="mt-3 p-3 rounded-xl border flex items-center justify-between flex-wrap gap-2 text-xs"
        :class="hasScenarioGap ? 'bg-red-50 border-red-200 text-red-900' : 'bg-emerald-50/80 border-emerald-200 text-emerald-900'"
      >
        <div class="flex items-center space-x-2.5">
          <component :is="hasScenarioGap ? AlertOctagon : CheckCircle2" class="w-5 h-5 shrink-0" :class="hasScenarioGap ? 'text-red-600' : 'text-emerald-600'" />
          <div>
            <span class="font-extrabold">
              {{ hasScenarioGap ? 'Внимание: смоделирован кассовый разрыв!' : 'Запас прочности подтвержден:' }}
            </span>
            <span class="ml-1" :class="hasScenarioGap ? 'text-red-800' : 'text-emerald-800'">
              {{ hasScenarioGap ? 'Рекомендуется заранее согласовать отсрочку поставщикам или факторинг дебиторки.' : 'бизнес выдерживает данный стресс-тест без ухода в дефицит.' }}
            </span>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Sliders,
  XCircle,
  Info,
  AlertOctagon,
  CheckCircle2,
  Plus
} from 'lucide-vue-next'
import ScenarioChart from '~/components/charts/ScenarioChart.vue'
import { formatMoney } from '~/utils/format'

defineEmits(['open-custom-scenario'])

const { activeCompanyId } = useCompany()
const {
  activeScenarioId,
  scenarioHorizon,
  scenarioParams,
  comparisonData,
  setScenario,
  fetchComparison
} = useScenarios()

const activeScenarioTitle = computed(() => {
  switch (activeScenarioId.value) {
    case 'drop':
      return 'Спад выручки'
    case 'expense':
      return 'Внеплановый крупный расход'
    case 'cost':
      return 'Рост постоянных трат'
    default:
      return 'Задержка оплаты дебитора'
  }
})

const scenarioMechanismText = computed(() => {
  switch (activeScenarioId.value) {
    case 'drop':
      return 'Пропорционально уменьшает все прогнозируемые операционные поступления от контрагентов и эквайринга на выбранную долю.'
    case 'expense':
      return 'Симулирует штраф ФНС, поломку оборудования, срочную закупку сырья или доначисление налогов на выбранную сумму.'
    case 'cost':
      return 'Индексирует регулярные слоты обязательств (аренда, ФОТ, логистика, коммунальные услуги) на выбранный процент.'
    default:
      return 'Сдвигает платежи ключевых покупателей на указанный срок. Показывает точную глубину кассового провала и дату возврата к норме.'
  }
})

const minScenarioBalance = computed(() => {
  if (comparisonData.value?.scenario_min_balance !== undefined) {
    return comparisonData.value.scenario_min_balance
  }
  const pts = comparisonData.value?.comparison || []
  if (pts.length > 0) {
    return Math.min(...pts.map(p => p.scenario_p50))
  }
  return 0
})

const hasScenarioGap = computed(() => {
  return minScenarioBalance.value < 0 || !!comparisonData.value?.scenario_first_gap
})

const stressDelta = computed(() => {
  if (comparisonData.value?.scenario_end_balance !== undefined && comparisonData.value?.baseline_end_balance !== undefined) {
    return comparisonData.value.scenario_end_balance - comparisonData.value.baseline_end_balance
  }
  return 0
})

let debounceTimer: any = null
const onParamChange = () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    if (activeCompanyId.value) {
      fetchComparison(activeCompanyId.value)
    }
  }, 150)
}

const selectPreset = (type: string) => {
  setScenario(type)
  if (activeCompanyId.value) {
    fetchComparison(activeCompanyId.value)
  }
}

const changeHorizon = (h: number) => {
  scenarioHorizon.value = h
  if (activeCompanyId.value) {
    fetchComparison(activeCompanyId.value)
  }
}

const cancelScenario = () => {
  scenarioParams.value = {
    delay_days: 0,
    drop_percent: 0,
    amount: 0,
    increase_percent: 0,
    expense_days_ahead: 5
  }
  onParamChange()
}
</script>
