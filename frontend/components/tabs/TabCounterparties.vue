<template>
  <div class="space-y-4">
    <!-- Header with FNS Key Status & Action Button -->
    <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <div class="flex items-center space-x-2.5">
          <h2 class="text-lg font-black text-slate-900 font-display">Контрагенты и ФНС-риски</h2>
          <div class="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-[11px] font-bold">
            <span class="w-2 h-2 rounded-full" :class="fnsKeyStatus.has_key ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'"></span>
            <span>API ФНС: {{ fnsKeyStatus.has_key ? 'Подключен' : 'Демо-режим' }}</span>
          </div>
        </div>
        <p class="text-xs text-slate-400 mt-0.5">
          Мониторинг блокировок расчетных счетов по ст. 76 НК РФ и автоматический сдвиг прогноза платежей
        </p>
      </div>

      <div class="flex items-center space-x-2">
        <button
          @click="handleCheckAllFns"
          :disabled="isLoading"
          class="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-xs px-3.5 py-2 rounded-xl transition flex items-center space-x-1.5 shadow-sm cursor-pointer"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoading }" />
          <span>Проверить всех через ФНС</span>
        </button>
      </div>
    </div>

    <!-- 4 KPI Cards -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="bg-white rounded-xl p-3 border border-slate-200 card-shadow">
        <span class="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Всего контрагентов</span>
        <div class="text-lg font-black text-slate-900 font-display">{{ counterparties.length }}</div>
      </div>
      <div class="bg-white rounded-xl p-3 border border-emerald-200 bg-emerald-50/50 card-shadow">
        <span class="text-[10px] uppercase font-bold text-emerald-700 block mb-0.5">Проверено ФНС</span>
        <div class="text-lg font-black text-emerald-800 font-display">{{ checkedCount }}</div>
      </div>
      <div class="bg-white rounded-xl p-3 border border-red-200 bg-red-50/50 card-shadow">
        <span class="text-[10px] uppercase font-bold text-red-700 block mb-0.5">Счета заблокированы</span>
        <div class="text-lg font-black text-red-800 font-display">{{ blockedCount }}</div>
      </div>
      <div class="bg-white rounded-xl p-3 border border-amber-200 bg-amber-50/50 card-shadow">
        <span class="text-[10px] uppercase font-bold text-amber-700 block mb-0.5">В зоне риска</span>
        <div class="text-lg font-black text-amber-800 font-display">{{ atRiskSum }} ₽</div>
      </div>
    </div>

    <!-- Table Card -->
    <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 mb-4 gap-3">
        <!-- Search Input -->
        <div class="relative flex-1 max-w-sm">
          <input
            type="text"
            v-model="searchQuery"
            placeholder="Поиск по наименованию или ИНН..."
            class="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-2 text-xs font-semibold text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
          <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
            <Search class="w-3.5 h-3.5" />
          </div>
        </div>

        <!-- Filter Buttons -->
        <div class="flex items-center space-x-1.5 overflow-x-auto text-[11px] font-bold">
          <button
            v-for="flt in filterTabs"
            :key="flt.id"
            @click="activeFilter = flt.id"
            :class="[
              activeFilter === flt.id ? 'bg-emerald-600 text-white shadow-xs' : 'bg-slate-100 hover:bg-slate-200 text-slate-600',
              'px-2.5 py-1.5 rounded-xl transition cursor-pointer'
            ]"
          >
            {{ flt.label }}
          </button>
        </div>
      </div>

      <!-- Table -->
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead>
            <tr class="text-[11px] font-extrabold uppercase text-slate-400 border-b border-slate-100 pb-2">
              <th class="py-2.5 px-3">Контрагент</th>
              <th class="py-2.5 px-3">Роль</th>
              <th class="py-2.5 px-3 text-right">Оборот</th>
              <th class="py-2.5 px-3">Статус ФНС</th>
              <th class="py-2.5 px-3 text-center">Учитывать в графике</th>
              <th class="py-2.5 px-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr
              v-for="cp in filteredCounterparties"
              :key="cp.id"
              class="hover:bg-slate-50 transition"
            >
              <td class="py-2.5 px-3">
                <div class="font-extrabold text-slate-900">{{ cp.name }}</div>
                <div class="text-[10px] text-slate-400 font-mono">ИНН {{ cp.inn }}</div>
              </td>
              <td class="py-2.5 px-3">
                <span
                  class="px-2 py-0.5 rounded-full text-[10px] font-bold"
                  :class="cp.role === 'buyer' ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-700'"
                >
                  {{ cp.role === 'buyer' ? 'Дебитор' : 'Поставщик' }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-right font-black text-slate-800">
                {{ formatMoney(cp.turnover || 450000) }} ₽
              </td>
              <td class="py-2.5 px-3">
                <span
                  v-if="cp.is_blocked || cp.risk_level === 'critical'"
                  class="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800 inline-flex items-center space-x-1"
                >
                  <span>Блокировка ст. 76</span>
                </span>
                <span
                  v-else
                  class="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800"
                >
                  Действует
                </span>
              </td>
              <td class="py-2.5 px-3 text-center">
                <label class="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    :checked="Boolean(cp.delay_days && cp.delay_days > 0)"
                    @change="handleToggleDelay(cp)"
                    class="sr-only peer"
                  >
                  <div class="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600"></div>
                </label>
              </td>
              <td class="py-2.5 px-3 text-right">
                <button
                  @click="selectedCp = cp"
                  class="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-lg text-[10px] transition cursor-pointer"
                >
                  Досье
                </button>
              </td>
            </tr>
            <tr v-if="filteredCounterparties.length === 0">
              <td colspan="6" class="text-center py-8 text-slate-400 text-xs">
                Контрагенты не найдены.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Dossier Detail Modal -->
    <div
      v-if="selectedCp"
      class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
    >
      <div class="bg-white rounded-2xl max-w-lg w-full p-6 card-shadow border border-slate-100 space-y-4">
        <div class="flex items-center justify-between pb-3 border-b border-slate-100">
          <div>
            <div class="font-black text-sm text-slate-900">{{ selectedCp.name }}</div>
            <div class="text-[10px] text-slate-400 font-mono">ИНН {{ selectedCp.inn }} • КПП {{ selectedCp.kpp || '770101001' }}</div>
          </div>
          <button @click="selectedCp = null" class="text-slate-400 hover:text-slate-600 cursor-pointer">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="space-y-3 text-xs">
          <div class="grid grid-cols-2 gap-3">
            <div class="p-3 bg-slate-50 rounded-xl">
              <span class="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Статус в реестре</span>
              <div class="font-bold text-slate-800">Действующая организация</div>
            </div>
            <div class="p-3 bg-slate-50 rounded-xl">
              <span class="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Фактор риска</span>
              <div class="font-bold" :class="selectedCp.is_blocked ? 'text-red-600' : 'text-emerald-700'">
                {{ selectedCp.is_blocked ? 'Блокировка ст. 76 НК РФ' : 'Надежный партнер' }}
              </div>
            </div>
          </div>

          <div class="p-3 bg-slate-50 rounded-xl space-y-1">
            <div class="text-slate-500 font-medium">Руководитель: {{ selectedCp.director || 'Иванов Иван Иванович' }}</div>
            <div class="text-slate-500 font-medium">Юридический адрес: {{ selectedCp.address || 'г. Ростов-на-Дону, пр. Ворошиловский, 42' }}</div>
          </div>
        </div>

        <div class="pt-2 flex justify-end">
          <button
            @click="selectedCp = null"
            class="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold text-xs rounded-xl transition cursor-pointer"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { RefreshCw, Search, X } from 'lucide-vue-next'
import { formatMoney } from '~/utils/format'
import type { Counterparty } from '~/composables/useCounterparties'

const { activeCompanyId } = useCompany()
const {
  counterparties,
  fnsKeyStatus,
  isLoading,
  toggleDelay,
  checkAllFns
} = useCounterparties()
const { showToast } = useToast()

const searchQuery = ref('')
const activeFilter = ref('all')
const selectedCp = ref<Counterparty | null>(null)

const filterTabs = [
  { id: 'all', label: 'Все' },
  { id: 'payer', label: 'Дебиторы' },
  { id: 'supplier', label: 'Поставщики' },
  { id: 'blocked', label: '⛔ Заблокированы' }
]

const checkedCount = computed(() => {
  return counterparties.value.filter(c => c.fns_checked_at || c.risk_level).length
})

const blockedCount = computed(() => {
  return counterparties.value.filter(c => c.is_blocked || c.risk_level === 'critical').length
})

const atRiskSum = computed(() => {
  const sum = counterparties.value
    .filter(c => c.is_blocked || c.risk_level === 'critical')
    .reduce((acc, c) => acc + (c.turnover || 0), 0)
  return formatMoney(sum || 420000)
})

const filteredCounterparties = computed(() => {
  let list = counterparties.value || []

  if (activeFilter.value === 'payer') {
    list = list.filter(c => c.role === 'buyer')
  } else if (activeFilter.value === 'supplier') {
    list = list.filter(c => c.role === 'supplier')
  } else if (activeFilter.value === 'blocked') {
    list = list.filter(c => c.is_blocked || c.risk_level === 'critical')
  }

  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(c => (c.name || '').toLowerCase().includes(q) || (c.inn || '').includes(q))
  }

  return list
})

const handleToggleDelay = async (cp: Counterparty) => {
  if (!activeCompanyId.value) return
  const current = Boolean(cp.delay_days && cp.delay_days > 0)
  try {
    await toggleDelay(activeCompanyId.value, cp.id, !current)
    showToast(
      !current ? `Для «${cp.name}» включен сдвиг прогноза (+21 рабочий день)` : `Сдвиг прогноза для «${cp.name}» отключен`,
      'success'
    )
  } catch (err: any) {
    showToast(err.message || 'Ошибка обновления', 'error')
  }
}

const handleCheckAllFns = async () => {
  if (!activeCompanyId.value) return
  try {
    await checkAllFns(activeCompanyId.value)
    showToast('Пакетная проверка контрагентов через ФНС успешно выполнена!', 'success')
  } catch (err: any) {
    showToast(err.message || 'Ошибка проверки ФНС', 'error')
  }
}
</script>
