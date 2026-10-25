<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
  >
    <div class="bg-white rounded-3xl max-w-lg w-full p-6 card-shadow border border-slate-100 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-100">
        <div class="flex items-center space-x-2">
          <div
            class="w-8 h-8 rounded-xl flex items-center justify-center font-black"
            :class="direction === 'inflow' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-800'"
          >
            <component :is="direction === 'inflow' ? Plus : Minus" class="w-4 h-4" />
          </div>
          <div>
            <h3 class="text-sm font-black text-slate-900">
              {{ direction === 'inflow' ? 'Запланировать поступление (+)' : 'Запланировать платеж (-)' }}
            </h3>
            <p class="text-[10px] text-slate-400">Событие будет учтено в графике прогноза кассового радара</p>
          </div>
        </div>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 cursor-pointer">
          <X class="w-4 h-4" />
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-3 text-xs">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Сумма операции (₽): *</label>
          <input
            type="number"
            step="1000"
            min="1"
            v-model.number="form.amount"
            required
            placeholder="Например: 150000"
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-black text-sm text-slate-900 focus:ring-2 focus:ring-ci-500"
          >
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block font-bold text-slate-700 mb-1">Дата события: *</label>
            <input
              type="date"
              v-model="form.event_date"
              required
              class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
            >
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">Категория:</label>
            <select
              v-model="form.category"
              class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
            >
              <option value="cat_revenue_client">Поступления от покупателей</option>
              <option value="cat_procurement">Закупка товаров</option>
              <option value="cat_payroll">Зарплата и ФОТ</option>
              <option value="cat_rent">Аренда</option>
              <option value="cat_taxes">Налоги (ЕНП)</option>
              <option value="cat_other">Прочее</option>
            </select>
          </div>
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">Контрагент / Назначение: *</label>
          <input
            type="text"
            v-model="form.counterparty_name"
            required
            placeholder="ООО «Ромашка» / Оплата по договору №12"
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
          >
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">ИНН контрагента (опционально):</label>
          <input
            type="text"
            v-model="form.counterparty_inn"
            placeholder="10 или 12 цифр"
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500 font-mono"
          >
        </div>

        <div>
          <div class="flex justify-between items-center mb-1">
            <label class="font-bold text-slate-700">Вероятность платежа:</label>
            <span class="font-black text-ci-700">{{ Math.round((form.probability || 1) * 100) }}%</span>
          </div>
          <input
            type="range"
            min="0.1"
            max="1.0"
            step="0.05"
            v-model.number="form.probability"
            class="w-full accent-ci-600 cursor-pointer"
          >
          <span class="text-[10px] text-slate-400 block mt-0.5">
            100% — подтвержденный платеж, 50-80% — ожидается с вероятностью
          </span>
        </div>

        <div class="pt-3 border-t border-slate-100 flex items-center justify-end space-x-2">
          <button
            type="button"
            @click="$emit('close')"
            class="px-3.5 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
          >
            Отмена
          </button>
          <button
            type="submit"
            :disabled="isSubmitting"
            class="px-5 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl transition shadow-sm cursor-pointer"
          >
            {{ isSubmitting ? 'Сохранение...' : 'Добавить в прогноз' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Plus, Minus, X } from 'lucide-vue-next'

const props = defineProps<{
  isOpen: boolean
  direction: 'inflow' | 'outflow'
}>()

const emit = defineEmits(['close', 'saved'])

const { activeCompanyId } = useCompany()
const { addEvent } = useForecast()
const { showToast } = useToast()

const isSubmitting = ref(false)

const getTomorrow = () => {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().split('T')[0]
}

const form = ref({
  amount: 150000,
  event_date: getTomorrow(),
  category: 'cat_revenue_client',
  counterparty_name: '',
  counterparty_inn: '',
  probability: 1.0
})

watch(() => props.direction, (dir) => {
  form.value.category = dir === 'inflow' ? 'cat_revenue_client' : 'cat_procurement'
})

const handleSubmit = async () => {
  if (!activeCompanyId.value) return
  if (form.value.amount <= 0) {
    showToast('Введите корректную сумму операции больше нуля', 'warning')
    return
  }

  // Validate INN if provided
  if (form.value.counterparty_inn) {
    const cleanInn = form.value.counterparty_inn.trim()
    if (!/^\d+$/.test(cleanInn) || (cleanInn.length !== 10 && cleanInn.length !== 12)) {
      showToast('ИНН контрагента должен состоять из 10 (для ЮЛ) или 12 (для ИП) цифр', 'warning')
      return
    }
  }

  isSubmitting.value = true
  try {
    const signedAmount = props.direction === 'inflow' ? Math.abs(form.value.amount) : -Math.abs(form.value.amount)
    await addEvent(activeCompanyId.value, {
      event_date: form.value.event_date,
      amount: signedAmount,
      description: form.value.counterparty_name,
      counterparty_name: form.value.counterparty_name,
      counterparty_inn: form.value.counterparty_inn || '7707083893',
      category: form.value.category,
      probability: form.value.probability
    })

    showToast(
      props.direction === 'inflow' ? 'Поступление успешно добавлено в прогноз!' : 'Расход успешно запланирован!',
      'success'
    )
    emit('saved')
    emit('close')
  } catch (err: any) {
    showToast(err.message || 'Ошибка сохранения события', 'error')
  } finally {
    isSubmitting.value = false
  }
}
</script>
