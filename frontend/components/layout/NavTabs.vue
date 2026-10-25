<template>
  <div class="max-w-6xl w-full mx-auto px-4 sm:px-6 lg:px-8 -mt-2">
    <div class="flex items-center justify-between bg-white rounded-2xl p-2.5 card-shadow border border-slate-100 gap-2 flex-wrap">
      
      <!-- Action buttons -->
      <div class="flex items-center space-x-2">
        <button
          @click="$emit('open-event-modal', 'inflow')"
          class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs px-3.5 py-2 rounded-xl flex items-center space-x-1.5 shadow-sm transition cursor-pointer"
        >
          <Plus class="w-3.5 h-3.5" />
          <span>Жду оплату</span>
        </button>
        <button
          @click="$emit('open-event-modal', 'outflow')"
          class="bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs px-3.5 py-2 rounded-xl flex items-center space-x-1.5 transition cursor-pointer"
        >
          <Minus class="w-3.5 h-3.5" />
          <span>Заплачу</span>
        </button>
      </div>

      <!-- Navigation Pills -->
      <nav class="flex items-center space-x-1.5 overflow-x-auto hide-scrollbar py-1 text-xs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="$emit('update:activeTab', tab.id)"
          :class="[
            activeTab === tab.id ? 'pill-active shadow-xs' : 'pill-inactive',
            'px-3.5 py-1.5 rounded-xl transition flex items-center space-x-1.5 cursor-pointer relative'
          ]"
        >
          <span>{{ tab.label }}</span>
          <span
            v-if="tab.id === 'breakdown' && hasAlertRisk"
            class="w-2 h-2 rounded-full bg-red-400 animate-pulse ml-0.5"
          ></span>
        </button>
      </nav>

    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Minus } from 'lucide-vue-next'

const props = defineProps<{
  activeTab: string
}>()

defineEmits(['update:activeTab', 'open-event-modal'])

const { currentAlert } = useAlerts()

const hasAlertRisk = computed(() => {
  return currentAlert.value && (currentAlert.value.level === 'critical' || currentAlert.value.level === 'warning')
})

const tabs = [
  { id: 'radar', label: 'Радар' },
  { id: 'breakdown', label: 'Разбор' },
  { id: 'scenarios', label: 'Сценарии' },
  { id: 'operations', label: 'Операции' },
  { id: 'counterparties', label: 'Контрагенты' },
  { id: 'cabinet', label: 'Кабинет' }
]
</script>
