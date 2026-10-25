<template>
  <div class="text-slate-800 antialiased min-h-screen flex flex-col bg-[#F8FAFC]">
    
    <!-- Top Header -->
    <AppHeader
      @switch-tab="activeTab = $event"
      @open-balance-modal="showBalanceModal = true"
      @open-add-business="showAddBusinessModal = true"
    />

    <!-- Quick Action Pills & Tabs (under header) -->
    <NavTabs
      :active-tab="activeTab"
      @update:active-tab="handleTabChange"
      @open-event-modal="openEventModal"
    />

    <!-- Main Body Container -->
    <main class="flex-grow max-w-6xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-5">
      
      <!-- Clean Business Onboarding Banner (if statement not yet loaded) -->
      <div
        v-if="activeCompany && !hasStatement"
        class="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-slate-800 card-shadow flex items-center justify-between flex-wrap gap-3"
      >
        <div class="flex items-center space-x-3">
          <div class="w-8 h-8 rounded-xl bg-amber-500 text-white flex items-center justify-center shrink-0">
            <FileText class="w-4 h-4" />
          </div>
          <div>
            <div class="text-xs font-black text-amber-950">Новый расчетный счет: выписка не загружена</div>
            <div class="text-[11px] text-amber-800">Загрузите файл выписки в Личном кабинете для формирования календаря и графика остатков</div>
          </div>
        </div>
        <div class="flex items-center space-x-2 text-xs">
          <button
            @click="showUploadModal = true"
            class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 rounded-xl transition flex items-center space-x-1.5 shadow-sm cursor-pointer"
          >
            <UploadCloud class="w-3.5 h-3.5" />
            <span>Загрузить выписку</span>
          </button>
          <button
            @click="setCompany('C001')"
            class="bg-white hover:bg-amber-100 text-amber-900 border border-amber-300 font-bold px-2.5 py-1.5 rounded-xl transition cursor-pointer"
          >
            Демо C001
          </button>
          <button
            @click="setCompany('C004')"
            class="bg-white hover:bg-red-50 text-red-800 border border-red-200 font-bold px-2.5 py-1.5 rounded-xl transition cursor-pointer"
          >
            Демо C004
          </button>
        </div>
      </div>

      <!-- Tab 1: Radar -->
      <TabRadar
        v-if="activeTab === 'radar'"
        @switch-tab="activeTab = $event"
        @open-event-modal="openEventModal"
      />

      <!-- Tab 2: Breakdown (GigaChat AI) -->
      <TabBreakdown
        v-else-if="activeTab === 'breakdown'"
        @switch-tab="activeTab = $event"
      />

      <!-- Tab 3: Scenarios -->
      <TabScenarios
        v-else-if="activeTab === 'scenarios'"
        @open-custom-scenario="showCustomScenarioModal = true"
      />

      <!-- Tab 4: Operations -->
      <TabOperations
        v-else-if="activeTab === 'operations'"
        @open-upload-modal="showUploadModal = true"
      />

      <!-- Tab 5: Counterparties -->
      <TabCounterparties
        v-else-if="activeTab === 'counterparties'"
      />

      <!-- Tab 6: Cabinet -->
      <TabCabinet
        v-else-if="activeTab === 'cabinet'"
      />
    </main>

    <!-- Footer -->
    <footer class="py-6 border-t border-slate-200 bg-white text-center text-xs text-slate-400">
      <div class="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
        <div class="flex items-center space-x-2">
          <span class="font-bold text-slate-600">Банк «Центр-инвест»</span>
          <span>•</span>
          <span>ПАО КБ «Центр-инвест» Ген. лицензия ЦБ РФ № 2225</span>
        </div>
        <div>
          Кассовый Радар v2.6 Nuxt 3 Edition • ML & Monte Carlo & GigaChat
        </div>
      </div>
    </footer>

    <!-- Global Modals -->
    <EventModal
      :is-open="showEventModal"
      :direction="eventModalDirection"
      @close="showEventModal = false"
    />

    <BalanceModal
      :is-open="showBalanceModal"
      @close="showBalanceModal = false"
    />

    <UploadModal
      :is-open="showUploadModal"
      @close="showUploadModal = false"
    />

    <AddBusinessModal
      :is-open="showAddBusinessModal"
      @close="showAddBusinessModal = false"
    />

    <ScenarioModal
      :is-open="showCustomScenarioModal"
      @close="showCustomScenarioModal = false"
    />

    <AuthModal />

    <!-- Toast Notifications -->
    <ToastContainer />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { FileText, UploadCloud } from 'lucide-vue-next'
import AppHeader from '~/components/layout/AppHeader.vue'
import NavTabs from '~/components/layout/NavTabs.vue'
import ToastContainer from '~/components/layout/ToastContainer.vue'
import TabRadar from '~/components/tabs/TabRadar.vue'
import TabBreakdown from '~/components/tabs/TabBreakdown.vue'
import TabScenarios from '~/components/tabs/TabScenarios.vue'
import TabOperations from '~/components/tabs/TabOperations.vue'
import TabCounterparties from '~/components/tabs/TabCounterparties.vue'
import TabCabinet from '~/components/tabs/TabCabinet.vue'
import EventModal from '~/components/modals/EventModal.vue'
import BalanceModal from '~/components/modals/BalanceModal.vue'
import UploadModal from '~/components/modals/UploadModal.vue'
import AddBusinessModal from '~/components/modals/AddBusinessModal.vue'
import ScenarioModal from '~/components/modals/ScenarioModal.vue'
import AuthModal from '~/components/modals/AuthModal.vue'

const activeTab = ref('radar')

const showEventModal = ref(false)
const eventModalDirection = ref<'inflow' | 'outflow'>('inflow')
const showBalanceModal = ref(false)
const showUploadModal = ref(false)
const showAddBusinessModal = ref(false)
const showCustomScenarioModal = ref(false)

const { fetchCompanies, activeCompanyId, activeCompany, setCompany } = useCompany()
const { initAuth } = useAuth()
const { fetchForecast, fetchEvents } = useForecast()
const { fetchAlerts, refreshAIBreakdown, currentAlert } = useAlerts()
const { fetchOperations } = useOperations()
const { fetchCounterparties, fetchFnsKeyStatus } = useCounterparties()
const { fetchComparison } = useScenarios()

const hasStatement = computed(() => {
  return true // default true for demos
})

const openEventModal = (direction: 'inflow' | 'outflow') => {
  eventModalDirection.value = direction
  showEventModal.value = true
}

const handleTabChange = async (newTab: string) => {
  activeTab.value = newTab
  if (newTab === 'breakdown') {
    // If opening breakdown and no ai_reason is yet generated, trigger GigaChat automatically
    if (activeCompanyId.value && currentAlert.value && !currentAlert.value.ai_reason) {
      await refreshAIBreakdown(activeCompanyId.value)
    }
  }
}

const loadAllData = async (compId: string) => {
  if (!compId) return
  await Promise.allSettled([
    fetchForecast(compId),
    fetchAlerts(compId),
    fetchEvents(compId),
    fetchOperations(compId),
    fetchCounterparties(compId),
    fetchFnsKeyStatus(compId),
    fetchComparison(compId)
  ])
}

onMounted(async () => {
  await fetchCompanies()
  await initAuth()
  if (activeCompanyId.value) {
    await loadAllData(activeCompanyId.value)
  }
})

watch(() => activeCompanyId.value, async (newId) => {
  if (newId) {
    await loadAllData(newId)
  }
})
</script>
