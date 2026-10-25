<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
  >
    <div class="bg-white rounded-3xl max-w-lg w-full p-6 card-shadow border border-slate-100 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-100">
        <div class="flex items-center space-x-2">
          <div class="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold">
            <Briefcase class="w-4 h-4" />
          </div>
          <div>
            <h3 class="text-sm font-black text-slate-900">Добавить новый бизнес в аккаунт</h3>
            <p class="text-[10px] text-slate-400">Мульти-бизнес управление в едином окне</p>
          </div>
        </div>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 cursor-pointer">
          <X class="w-4 h-4" />
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-3 text-xs">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Название организации или ФИО ИП: *</label>
          <input
            type="text"
            v-model="form.name"
            required
            placeholder="ООО «Южный Вектор» или ИП Петров А.В."
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
          >
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block font-bold text-slate-700 mb-1">Организационно-правовая форма: *</label>
            <select
              v-model="form.legal_form"
              class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
            >
              <option value="ООО">ООО (Юр. лицо, 10 цифр)</option>
              <option value="ИП">ИП (12 цифр)</option>
              <option value="АО">АО (10 цифр)</option>
              <option value="Самозанятый">Самозанятый (12 цифр)</option>
            </select>
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">ИНН: *</label>
            <input
              type="text"
              v-model="form.inn"
              required
              :placeholder="form.legal_form === 'ИП' || form.legal_form === 'Самозанятый' ? '12 цифр' : '10 цифр'"
              class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500 font-mono"
            >
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block font-bold text-slate-700 mb-1">Отрасль деятельности:</label>
            <select
              v-model="form.industry"
              class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
            >
              <option value="Оптовая торговля">Оптовая торговля</option>
              <option value="Розничная торговля">Розничная торговля</option>
              <option value="Услуги и сервис">Услуги и сервис</option>
              <option value="Производство">Производство</option>
              <option value="IT и разработка">IT и разработка</option>
              <option value="Логистика">Логистика</option>
            </select>
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">Система налогообложения:</label>
            <select
              v-model="form.tax_regime"
              class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
            >
              <option value="УСН «Доходы» 6%">УСН «Доходы» 6%</option>
              <option value="УСН «Доходы минус расходы» 15%">УСН «Доходы минус расходы» 15%</option>
              <option value="ОСНО">ОСНО (Общая с НДС)</option>
              <option value="Патент (ПСН)">Патент (ПСН)</option>
            </select>
          </div>
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">Стартовый остаток на расчетном счете (₽):</label>
          <input
            type="number"
            min="0"
            step="1000"
            v-model.number="form.initial_balance"
            placeholder="0"
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-black text-sm text-slate-900 focus:ring-2 focus:ring-ci-500"
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
            :disabled="isSubmitting"
            class="px-5 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl transition shadow-sm cursor-pointer"
          >
            {{ isSubmitting ? 'Создание...' : 'Создать бизнес' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Briefcase, X } from 'lucide-vue-next'
import { validateInnAndName } from '~/utils/format'

defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits(['close', 'created'])

const { createCompany } = useCompany()
const { fetchForecast } = useForecast()
const { showToast } = useToast()

const isSubmitting = ref(false)

const form = ref({
  name: '',
  legal_form: 'ООО',
  inn: '',
  industry: 'Оптовая торговля',
  tax_regime: 'УСН «Доходы» 6%',
  initial_balance: 0
})

const handleSubmit = async () => {
  const err = validateInnAndName(form.value.inn, form.value.legal_form, form.value.name)
  if (err) {
    showToast(err, 'warning')
    return
  }

  isSubmitting.value = true
  try {
    const comp = await createCompany({
      name: form.value.name,
      inn: form.value.inn,
      industry: form.value.industry,
      tax_system: form.value.tax_regime,
      balance: form.value.initial_balance
    })
    showToast(`Бизнес «${comp.name}» успешно добавлен в ваш аккаунт!`, 'success')
    await fetchForecast(comp.id)
    emit('created', comp)
    emit('close')
  } catch (err: any) {
    showToast(err.message || 'Ошибка создания бизнеса', 'error')
  } finally {
    isSubmitting.value = false
  }
}
</script>
