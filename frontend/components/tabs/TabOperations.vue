<template>
  <div class="space-y-4">
    <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100">
      
      <!-- Top header bar -->
      <div class="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <h2 class="text-lg font-black text-slate-900 font-display">Операции по счету</h2>
          <p class="text-xs text-slate-400">Разметка категорий, поиск и память правил классификации</p>
        </div>
        <div class="flex items-center space-x-2 flex-wrap gap-2">
          <!-- Quick Search Input -->
          <div class="relative w-48 sm:w-64">
            <input
              type="text"
              v-model="searchQuery"
              placeholder="Поиск по контрагенту или ИНН..."
              class="w-full bg-slate-50 border border-slate-200 rounded-xl pl-8 pr-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-ci-500 font-medium"
            >
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-2.5 text-slate-400">
              <Search class="w-3.5 h-3.5" />
            </div>
          </div>

          <!-- Direction Filter Pills -->
          <div class="flex bg-slate-100 p-1 rounded-xl text-xs font-bold">
            <button
              v-for="f in filterTypes"
              :key="f.id"
              @click="activeFilterType = f.id"
              :class="[
                activeFilterType === f.id ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900',
                'px-2.5 py-1 rounded-lg transition cursor-pointer'
              ]"
            >
              {{ f.label }}
            </button>
          </div>

          <!-- Statement Upload Button -->
          <button
            @click="$emit('open-upload-modal')"
            class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-1.5 rounded-xl transition flex items-center space-x-1.5 shadow-sm cursor-pointer"
          >
            <UploadCloud class="w-3.5 h-3.5" />
            <span>Загрузить выписку</span>
          </button>
        </div>
      </div>

      <!-- Operations Table -->
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-100 text-left text-xs">
          <thead class="text-slate-400 font-bold uppercase text-[10px]">
            <tr>
              <th class="py-2.5 px-3">Дата</th>
              <th class="py-2.5 px-3">Сумма</th>
              <th class="py-2.5 px-3">Контрагент и назначение</th>
              <th class="py-2.5 px-3">Категория</th>
              <th class="py-2.5 px-3 text-right">Действие</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr
              v-for="op in paginatedOperations"
              :key="op.id"
              class="hover:bg-slate-50 transition border-b border-slate-100"
            >
              <td class="py-2.5 px-3 whitespace-nowrap text-slate-500 font-medium">
                {{ formatDate(op.operation_date) }}
              </td>
              <td
                class="py-2.5 px-3 whitespace-nowrap font-black"
                :class="op.amount > 0 ? 'text-emerald-600' : 'text-slate-900'"
              >
                {{ op.amount > 0 ? '+' : '' }}{{ formatMoney(op.amount) }} ₽
              </td>
              <td class="py-2.5 px-3 max-w-[280px]">
                <div class="font-bold text-slate-800 truncate flex items-center space-x-1">
                  <span class="truncate">{{ op.counterparty_name || '—' }}</span>
                  <span v-if="op.counterparty_inn" class="text-[10px] text-slate-400 font-mono shrink-0 font-medium">
                    ({{ op.counterparty_inn }})
                  </span>
                </div>
                <div class="text-[10px] text-slate-400 truncate">
                  {{ op.payment_purpose || 'Платежное поручение' }}
                </div>
              </td>
              <td class="py-2.5 px-3">
                <span class="px-2 py-0.5 bg-slate-100 text-slate-700 rounded-lg text-[10px] font-bold">
                  {{ op.category_name || op.category_id || 'Основная деятельность' }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-right">
                <button
                  @click="openCategoryEdit(op)"
                  class="text-ci-600 hover:text-ci-800 font-bold text-[10px] bg-emerald-50 hover:bg-emerald-100 px-2 py-1 rounded-lg transition shadow-sm cursor-pointer"
                >
                  Правка
                </button>
              </td>
            </tr>
            <tr v-if="filteredOperations.length === 0">
              <td colspan="5" class="py-8 text-center text-slate-400 text-xs">
                Операции не найдены. Измените параметры фильтра или загрузите выписку.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="flex items-center justify-between pt-4 border-t border-slate-100 text-xs">
        <span class="text-slate-400">
          Показано {{ (currentPage - 1) * pageSize + 1 }}–{{ Math.min(currentPage * pageSize, filteredOperations.length) }} из {{ filteredOperations.length }}
        </span>
        <div class="flex items-center space-x-1">
          <button
            :disabled="currentPage === 1"
            @click="currentPage--"
            class="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-30 hover:bg-slate-50 transition cursor-pointer"
          >
            Назад
          </button>
          <span class="px-2 font-bold text-slate-700">Стр. {{ currentPage }} из {{ totalPages }}</span>
          <button
            :disabled="currentPage === totalPages"
            @click="currentPage++"
            class="px-2.5 py-1 rounded-lg border border-slate-200 disabled:opacity-30 hover:bg-slate-50 transition cursor-pointer"
          >
            Вперед
          </button>
        </div>
      </div>

    </div>

    <!-- Inline Category Edit Modal -->
    <div
      v-if="editingOperation"
      class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
    >
      <div class="bg-white rounded-2xl max-w-md w-full p-5 card-shadow border border-slate-100 space-y-4">
        <div class="flex items-center justify-between pb-3 border-b border-slate-100">
          <div class="font-black text-sm text-slate-900">Изменение категории операции</div>
          <button @click="editingOperation = null" class="text-slate-400 hover:text-slate-600 cursor-pointer">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="space-y-2 text-xs">
          <div class="p-3 bg-slate-50 rounded-xl space-y-1">
            <div class="font-extrabold text-slate-900">{{ editingOperation.counterparty_name || 'Контрагент' }}</div>
            <div class="text-slate-500 text-[11px]">{{ editingOperation.payment_purpose || 'Без описания' }}</div>
            <div class="font-black text-sm text-slate-900 pt-1">{{ formatMoney(editingOperation.amount) }} ₽</div>
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">Выберите категорию:</label>
            <select
              v-model="newCategory"
              class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-xs text-slate-800"
            >
              <option value="cat_revenue_client">Поступления от покупателей</option>
              <option value="cat_procurement">Закупка товаров и сырья</option>
              <option value="cat_payroll">Зарплата и ФОТ</option>
              <option value="cat_rent">Аренда помещений</option>
              <option value="cat_taxes">Налоги и сборы (ЕНП)</option>
              <option value="cat_logistics">Логистика и доставка</option>
              <option value="cat_marketing">Реклама и маркетинг</option>
              <option value="cat_other">Прочие расходы</option>
            </select>
          </div>

          <label class="flex items-center space-x-2 pt-1 cursor-pointer">
            <input type="checkbox" v-model="applyToSimilar" class="rounded text-ci-600">
            <span class="text-[11px] text-slate-600">Запомнить правило для будущих платежей этого контрагента</span>
          </label>
        </div>

        <div class="flex items-center justify-end space-x-2 pt-2">
          <button
            @click="editingOperation = null"
            class="px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
          >
            Отмена
          </button>
          <button
            @click="saveCategory"
            class="px-4 py-1.5 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl transition shadow-sm cursor-pointer"
          >
            Сохранить
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search, UploadCloud, X } from 'lucide-vue-next'
import { formatDate, formatMoney } from '~/utils/format'
import type { Operation } from '~/composables/useOperations'

defineEmits(['open-upload-modal'])

const { operations, updateCategory } = useOperations()
const { showToast } = useToast()

const searchQuery = ref('')
const activeFilterType = ref('all')
const currentPage = ref(1)
const pageSize = 15

const editingOperation = ref<Operation | null>(null)
const newCategory = ref('cat_revenue_client')
const applyToSimilar = ref(true)

const filterTypes = [
  { id: 'all', label: 'Все' },
  { id: 'inflow', label: 'Поступления (+)' },
  { id: 'outflow', label: 'Списания (-)' }
]

const filteredOperations = computed(() => {
  let list = operations.value || []

  if (activeFilterType.value === 'inflow') {
    list = list.filter(o => o.amount > 0)
  } else if (activeFilterType.value === 'outflow') {
    list = list.filter(o => o.amount < 0)
  }

  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(o => {
      const name = (o.counterparty_name || '').toLowerCase()
      const inn = (o.counterparty_inn || '').toLowerCase()
      const purp = (o.payment_purpose || '').toLowerCase()
      return name.includes(q) || inn.includes(q) || purp.includes(q)
    })
  }

  return list
})

const totalPages = computed(() => {
  return Math.max(1, Math.ceil(filteredOperations.value.length / pageSize))
})

const paginatedOperations = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredOperations.value.slice(start, start + pageSize)
})

const openCategoryEdit = (op: Operation) => {
  editingOperation.value = op
  newCategory.value = op.category_id || 'cat_other'
  applyToSimilar.value = true
}

const saveCategory = async () => {
  if (!editingOperation.value) return
  try {
    await updateCategory(editingOperation.value.id, newCategory.value, applyToSimilar.value)
    showToast('Категория успешно сохранена!', 'success')
    editingOperation.value = null
  } catch (err: any) {
    showToast(err.message || 'Ошибка сохранения', 'error')
  }
}
</script>
