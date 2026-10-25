<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
  >
    <div class="bg-white rounded-3xl max-w-md w-full p-6 card-shadow border border-slate-100 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-100">
        <div class="flex items-center space-x-2">
          <div class="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold">
            <Wallet class="w-4 h-4" />
          </div>
          <div>
            <h3 class="text-sm font-black text-slate-900">Корректировка остатка на счете</h3>
            <p class="text-[10px] text-slate-400">Счет: {{ activeCompany?.name }}</p>
          </div>
        </div>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 cursor-pointer">
          <X class="w-4 h-4" />
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-3 text-xs">
        <div class="p-3 bg-slate-50 rounded-xl space-y-1">
          <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">Текущий остаток</span>
          <div class="text-lg font-black text-slate-900 font-display">
            {{ formatMoney(activeCompany?.balance) }} ₽
          </div>
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">Новый остаток на счете (₽):</label>
          <input
            type="number"
            step="100"
            min="0"
            v-model.number="newBalance"
            required
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-black text-base text-slate-900 focus:ring-2 focus:ring-ci-500"
          >
          <p class="text-[10px] text-slate-500 mt-1 leading-snug">
            💡 Укажите <b>0</b>, чтобы сбросить остаток к фактическому расчетному значению из банковской выписки.
          </p>
        </div>

        <div class="pt-3 border-t border-slate-100 flex items-center justify-between">
          <button
            type="button"
            @click="newBalance = 0; handleSubmit()"
            class="text-[11px] font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
          >
            Сбросить к выписке (0 ₽)
          </button>
          <div class="flex items-center space-x-2">
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
              {{ isSubmitting ? 'Сохранение...' : 'Сохранить' }}
            </button>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Wallet, X } from 'lucide-vue-next'
import { formatMoney } from '~/utils/format'

const props = defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits(['close', 'saved'])

const { activeCompany, updateBalance } = useCompany()
const { fetchForecast } = useForecast()
const { showToast } = useToast()

const newBalance = ref<number>(0)
const isSubmitting = ref(false)

watch(() => props.isOpen, (open) => {
  if (open && activeCompany.value) {
    newBalance.value = activeCompany.value.balance || 0
  }
})

const handleSubmit = async () => {
  if (!activeCompany.value) return
  if (newBalance.value < 0) {
    showToast('Остаток на счете не может быть отрицательным', 'warning')
    return
  }

  isSubmitting.value = true
  try {
    await updateBalance(activeCompany.value.id, newBalance.value)
    await fetchForecast(activeCompany.value.id)
    showToast('Остаток на счете успешно обновлен!', 'success')
    emit('saved')
    emit('close')
  } catch (err: any) {
    showToast(err.message || 'Ошибка обновления остатка', 'error')
  } finally {
    isSubmitting.value = false
  }
}
</script>
