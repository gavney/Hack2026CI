<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
  >
    <div class="bg-white rounded-3xl max-w-md w-full p-6 card-shadow border border-slate-100 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-100">
        <div class="flex items-center space-x-2">
          <div class="w-8 h-8 rounded-xl bg-purple-100 text-purple-800 flex items-center justify-center font-bold">
            <Sliders class="w-4 h-4" />
          </div>
          <div>
            <h3 class="text-sm font-black text-slate-900">Пользовательский стресс-тест</h3>
            <p class="text-[10px] text-slate-400">Моделирование комплексного негативного фактора</p>
          </div>
        </div>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 cursor-pointer">
          <X class="w-4 h-4" />
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-3 text-xs">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Название сценария: *</label>
          <input
            type="text"
            v-model="customForm.name"
            required
            placeholder="Кассовый кризис: задержка + падение продаж"
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
          >
        </div>

        <div>
          <div class="flex justify-between items-center mb-1">
            <label class="font-bold text-slate-700">Задержка оплат от покупателей:</label>
            <span class="font-bold text-ci-700">+{{ customForm.delay_days }} дн</span>
          </div>
          <input
            type="range"
            min="0"
            max="60"
            step="1"
            v-model.number="customForm.delay_days"
            class="w-full accent-ci-600 cursor-pointer"
          >
        </div>

        <div>
          <div class="flex justify-between items-center mb-1">
            <label class="font-bold text-slate-700">Падение входящей выручки:</label>
            <span class="font-bold text-amber-700">-{{ customForm.drop_percent }}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="60"
            step="5"
            v-model.number="customForm.drop_percent"
            class="w-full accent-amber-600 cursor-pointer"
          >
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">Внеплановый расход (₽):</label>
          <input
            type="number"
            min="0"
            step="25000"
            v-model.number="customForm.amount"
            placeholder="0"
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2 font-black text-slate-900 focus:ring-2 focus:ring-ci-500"
          >
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
            class="px-5 py-2 text-xs font-bold bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition shadow-sm cursor-pointer"
          >
            Применить сценарий
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Sliders, X } from 'lucide-vue-next'

defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits(['close', 'applied'])

const { scenarioParams, setScenario, fetchComparison } = useScenarios()
const { activeCompanyId } = useCompany()
const { showToast } = useToast()

const customForm = ref({
  name: 'Комплексный стресс-тест',
  delay_days: 14,
  drop_percent: 15,
  amount: 200000
})

const handleSubmit = async () => {
  scenarioParams.value.delay_days = customForm.value.delay_days
  scenarioParams.value.drop_percent = customForm.value.drop_percent
  scenarioParams.value.amount = customForm.value.amount

  setScenario('delay')
  if (activeCompanyId.value) {
    await fetchComparison(activeCompanyId.value)
  }
  showToast(`Сценарий «${customForm.value.name}» успешно применен к расчету!`, 'success')
  emit('applied')
  emit('close')
}
</script>
