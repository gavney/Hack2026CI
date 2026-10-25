<template>
  <header class="wallet-header-bg text-white pb-6 pt-4 px-4 sm:px-6 lg:px-8 rounded-b-[2rem] shadow-md">
    <div class="max-w-6xl mx-auto">
      
      <!-- Top Bar: Logo, Company Picker, Profile -->
      <div class="flex items-center justify-between gap-3 mb-5">
        <!-- Logo -->
        <div class="flex items-center space-x-2.5">
          <div class="w-8 h-8 rounded-xl bg-white/20 backdrop-blur-md flex items-center justify-center text-white">
            <ShieldCheck class="w-5 h-5" />
          </div>
          <div>
            <span class="font-extrabold text-base tracking-tight leading-none block">Центр-инвест</span>
            <span class="text-[10px] text-emerald-100 uppercase tracking-wider font-semibold">Кассовый радар</span>
          </div>
        </div>

        <!-- Company Dropdown Selector & Multi-business Controls -->
        <div class="flex-1 max-w-md mx-2">
          <div class="relative flex items-center space-x-1.5">
            <div class="relative flex-grow">
              <select
                :value="activeCompanyId"
                @change="handleCompanyChange(($event.target as HTMLSelectElement).value)"
                class="w-full bg-white/15 hover:bg-white/20 text-white text-xs sm:text-sm font-semibold rounded-xl px-3 py-2 pr-8 border border-white/20 focus:outline-none focus:ring-2 focus:ring-white/40 appearance-none cursor-pointer truncate"
              >
                <option
                  v-for="c in companies"
                  :key="c.id"
                  :value="c.id"
                  class="text-slate-900 bg-white font-semibold"
                >
                  {{ c.name }} ({{ c.industry || 'Бизнес' }} • ИНН {{ c.inn }})
                </option>
                <option value="__add_new_business__" class="text-emerald-700 bg-emerald-50 font-bold">
                  + Добавить новый бизнес в аккаунт...
                </option>
              </select>
              <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-white/70">
                <ChevronDown class="w-4 h-4" />
              </div>
            </div>
            <!-- Quick Add Business Button -->
            <button
              @click="$emit('open-add-business')"
              title="Добавить бизнес в аккаунт"
              class="shrink-0 px-2.5 py-2 rounded-xl bg-white/15 hover:bg-white/30 text-white border border-white/20 transition flex items-center space-x-1 text-xs font-bold shadow-xs cursor-pointer"
            >
              <Plus class="w-3.5 h-3.5" />
              <span class="hidden sm:inline">+ Бизнес</span>
            </button>
          </div>
        </div>

        <!-- Notification & User Cabinet / Auth Group -->
        <div class="flex items-center space-x-2">
          <!-- Notification Bell -->
          <button
            @click="$emit('switch-tab', 'breakdown')"
            title="Уведомления"
            class="relative p-2 rounded-xl bg-white/15 hover:bg-white/20 text-white transition cursor-pointer"
          >
            <Bell class="w-4 h-4" />
            <span
              v-if="hasAlertRisk"
              class="absolute top-1 right-1 w-2.5 h-2.5 bg-red-400 rounded-full ring-2 ring-emerald-700 animate-pulse"
            ></span>
          </button>

          <!-- Logged In Controls Group -->
          <div v-if="currentUser" class="flex items-center space-x-1.5">
            <button
              @click="$emit('switch-tab', 'cabinet')"
              title="Личный кабинет бизнеса"
              class="flex items-center space-x-2 bg-white/15 hover:bg-white/25 border border-white/20 rounded-xl px-2.5 py-1.5 transition cursor-pointer"
            >
              <div class="w-6 h-6 rounded-lg bg-white text-emerald-800 flex items-center justify-center font-extrabold text-[11px]">
                {{ initials }}
              </div>
              <div class="hidden sm:block text-left text-xs leading-tight">
                <div class="font-bold truncate max-w-[120px]">{{ currentUser.full_name || 'Предприниматель' }}</div>
                <div class="text-[10px] text-emerald-100">Кабинет</div>
              </div>
            </button>

            <button
              @click="logout"
              title="Выйти из аккаунта"
              class="flex items-center space-x-1.5 bg-red-500/80 hover:bg-red-600 text-white border border-red-400/40 rounded-xl px-2.5 py-1.5 transition text-xs font-bold shadow-sm cursor-pointer"
            >
              <LogOut class="w-3.5 h-3.5" />
              <span class="hidden md:inline">Выйти</span>
            </button>
          </div>

          <!-- Logged Out / Guest Controls Group -->
          <div v-else class="flex items-center space-x-2">
            <button
              @click="openAuthModal"
              class="text-xs bg-white text-emerald-800 font-extrabold px-3 py-1.5 rounded-xl transition hover:bg-emerald-50 shadow-sm flex items-center space-x-1.5 cursor-pointer"
            >
              <LogIn class="w-3.5 h-3.5" />
              <span>Войти</span>
            </button>
            <button
              @click="openAuthModal"
              class="text-xs bg-white/20 hover:bg-white/30 text-white font-extrabold px-3 py-1.5 rounded-xl transition border border-white/30 flex items-center space-x-1.5 cursor-pointer"
            >
              <UserPlus class="w-3.5 h-3.5" />
              <span class="hidden sm:inline">Регистрация</span>
            </button>
          </div>
        </div>
      </div>

      <!-- SLEEK WALLET CARDS ROW -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3.5 pt-1">
        
        <!-- Card 1: Main Business Account -->
        <div class="bg-white text-slate-800 rounded-2xl p-4 card-shadow flex flex-col justify-between h-32 transition-transform hover:-translate-y-0.5">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <div class="w-7 h-7 rounded-lg bg-emerald-100 text-ci-700 flex items-center justify-center">
                <Wallet class="w-4 h-4" />
              </div>
              <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Текущий остаток</span>
            </div>
            <div class="flex items-center space-x-1.5">
              <span class="text-[10px] font-extrabold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                {{ activeCompany?.tax_system || 'ИП' }}
              </span>
              <button
                @click="$emit('open-balance-modal')"
                title="Изменить текущий остаток"
                class="text-slate-400 hover:text-emerald-700 p-1 hover:bg-emerald-50 rounded-lg transition cursor-pointer"
              >
                <Edit3 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <div>
            <div
              @click="$emit('open-balance-modal')"
              title="Нажмите для изменения остатка"
              class="text-2xl font-black text-slate-900 tracking-tight font-display cursor-pointer hover:text-emerald-700 transition"
            >
              {{ formatMoney(activeCompany?.balance) }} ₽
            </div>
            <div class="flex items-center justify-between text-[11px] text-slate-400 mt-0.5 font-medium">
              <span>Основной счет • ИНН {{ activeCompany?.inn || '—' }}</span>
              <span class="text-slate-500 font-medium">По выписке</span>
            </div>
          </div>
        </div>

        <!-- Card 2: Liquidity Radar Traffic Light -->
        <div class="bg-white text-slate-800 rounded-2xl p-4 card-shadow flex flex-col justify-between h-32 transition-transform hover:-translate-y-0.5">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span
                class="w-3 h-3 rounded-full"
                :class="hasAlertRisk ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'"
              ></span>
              <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Статус радара</span>
            </div>
            <span
              class="text-[10px] font-bold px-2 py-0.5 rounded-full border"
              :class="hasAlertRisk ? 'bg-red-50 text-red-700 border-red-200' : 'bg-emerald-50 text-emerald-800 border-emerald-200'"
            >
              {{ hasAlertRisk ? 'Риск 100%' : 'Риск 0%' }}
            </span>
          </div>
          <div>
            <div class="text-lg font-black text-slate-900 tracking-tight leading-tight">
              {{ hasAlertRisk ? 'Кассовый разрыв!' : 'Всё спокойно' }}
            </div>
            <p class="text-[11px] text-slate-500 mt-0.5 truncate">
              {{ hasAlertRisk ? (currentAlert?.message || 'Деньги могут закончиться в расчетном периоде') : 'Денег хватает на горизонте 30 дней.' }}
            </p>
          </div>
          <div class="text-right">
            <button
              @click="$emit('switch-tab', 'breakdown')"
              class="text-[11px] font-extrabold text-ci-600 hover:text-ci-800 inline-flex items-center space-x-0.5 cursor-pointer"
            >
              <span>Подробнее</span>
              <ChevronRight class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <!-- Card 3: Upcoming Key Obligation -->
        <div class="bg-white text-slate-800 rounded-2xl p-4 card-shadow flex flex-col justify-between h-32 transition-transform hover:-translate-y-0.5">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <div class="w-7 h-7 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center">
                <Calendar class="w-4 h-4" />
              </div>
              <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Ближайший платеж</span>
            </div>
            <span class="text-[10px] font-extrabold bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">График</span>
          </div>
          <div>
            <div class="text-xl font-black text-slate-900 tracking-tight font-display">
              {{ nextPaymentAmount }}
            </div>
            <div class="text-[11px] text-slate-500 mt-0.5 truncate">
              {{ nextPaymentDesc }}
            </div>
          </div>
          <div class="flex items-center justify-between text-[11px] text-slate-400">
            <span>Режим расчетов:</span>
            <span class="text-slate-700 font-extrabold">{{ activeCompany?.tax_system || 'УСН' }}</span>
          </div>
        </div>

      </div>

    </div>
  </header>
</template>

<script setup lang="ts">
import {
  ShieldCheck,
  Wallet,
  Edit3,
  Calendar,
  Plus,
  Bell,
  LogIn,
  UserPlus,
  LogOut,
  ChevronDown,
  ChevronRight
} from 'lucide-vue-next'
import { formatMoney } from '~/utils/format'

const emit = defineEmits([
  'switch-tab',
  'open-balance-modal',
  'open-add-business'
])

const { companies, activeCompanyId, activeCompany, setCompany } = useCompany()
const { currentUser, logout, openAuthModal } = useAuth()
const { currentAlert } = useAlerts()
const { futureEvents } = useForecast()

const hasAlertRisk = computed(() => {
  return currentAlert.value && (currentAlert.value.level === 'critical' || currentAlert.value.level === 'warning')
})

const initials = computed(() => {
  if (!currentUser.value?.full_name) return 'ИП'
  const parts = currentUser.value.full_name.trim().split(/\s+/)
  return parts.map(p => p[0]).join('').slice(0, 2).toUpperCase()
})

const nextPaymentAmount = computed(() => {
  const outflows = futureEvents.value.filter(e => e.amount < 0)
  if (outflows.length > 0) {
    return `${formatMoney(Math.abs(outflows[0].amount))} ₽`
  }
  return '225 983 ₽'
})

const nextPaymentDesc = computed(() => {
  const outflows = futureEvents.value.filter(e => e.amount < 0)
  if (outflows.length > 0) {
    return `${outflows[0].event_date} • ${outflows[0].description || outflows[0].counterparty_name || 'Плановый платеж'}`
  }
  return '28 число • ЕНП Налоги'
})

const handleCompanyChange = (val: string) => {
  if (val === '__add_new_business__') {
    emit('open-add-business')
  } else {
    setCompany(val)
  }
}
</script>
