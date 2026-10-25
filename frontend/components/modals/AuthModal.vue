<template>
  <div
    v-if="isAuthModalOpen"
    class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
  >
    <div class="bg-white rounded-3xl max-w-md w-full p-6 card-shadow border border-slate-100 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-100">
        <div class="flex items-center space-x-2">
          <div class="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold">
            <Lock class="w-4 h-4" />
          </div>
          <div>
            <h3 class="text-sm font-black text-slate-900">
              {{ isRegisterMode ? 'Регистрация в сервисе' : 'Вход в Кассовый радар' }}
            </h3>
            <p class="text-[10px] text-slate-400">Банк «Центр-инвест» • Защищенный доступ</p>
          </div>
        </div>
        <button @click="closeAuthModal" class="text-slate-400 hover:text-slate-600 cursor-pointer">
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Quick Demo Login Presets -->
      <div class="p-3 bg-emerald-50/70 border border-emerald-200/60 rounded-2xl space-y-2">
        <span class="text-[10px] font-bold text-emerald-800 uppercase tracking-wider block">
          Быстрый демо-вход в 1 клик:
        </span>
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            @click="quickDemoLogin('owner')"
            class="bg-white hover:bg-emerald-100 text-emerald-950 font-bold p-2 rounded-xl text-left border border-emerald-200 transition shadow-2xs text-xs cursor-pointer"
          >
            <div class="font-extrabold text-[11px]">Иван Смирнов</div>
            <div class="text-[10px] text-slate-500">Владелец бизнеса</div>
          </button>
          <button
            type="button"
            @click="quickDemoLogin('accountant')"
            class="bg-white hover:bg-emerald-100 text-emerald-950 font-bold p-2 rounded-xl text-left border border-emerald-200 transition shadow-2xs text-xs cursor-pointer"
          >
            <div class="font-extrabold text-[11px]">Анна Ковалева</div>
            <div class="text-[10px] text-slate-500">Главный бухгалтер</div>
          </button>
        </div>
      </div>

      <!-- SMS/OTP Form -->
      <form @submit.prevent="handleAuthSubmit" class="space-y-3 text-xs">
        <div v-if="isRegisterMode">
          <label class="block font-bold text-slate-700 mb-1">Ваше ФИО: *</label>
          <input
            type="text"
            v-model="authForm.fullName"
            placeholder="Иванов Иван Иванович"
            required
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
          >
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">Email или номер телефона: *</label>
          <input
            type="text"
            v-model="authForm.identifier"
            placeholder="ceo@business.ru или +7 (999) 000-00-00"
            required
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
          >
        </div>

        <div v-if="step === 'otp'">
          <label class="block font-bold text-slate-700 mb-1">Код подтверждения из SMS (6 цифр): *</label>
          <input
            type="text"
            v-model="authForm.code"
            maxlength="6"
            placeholder="123456"
            required
            class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-black text-center text-lg tracking-widest text-slate-900 focus:ring-2 focus:ring-ci-500 font-mono"
          >
        </div>

        <div class="pt-2 flex items-center justify-between text-xs">
          <button
            type="button"
            @click="isRegisterMode = !isRegisterMode; step = 'request'"
            class="text-ci-600 hover:underline font-bold cursor-pointer"
          >
            {{ isRegisterMode ? 'Уже есть аккаунт? Войти' : 'Нет аккаунта? Зарегистрироваться' }}
          </button>
        </div>

        <div class="pt-3 border-t border-slate-100 flex items-center justify-end space-x-2">
          <button
            type="button"
            @click="closeAuthModal"
            class="px-3.5 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
          >
            Отмена
          </button>
          <button
            type="submit"
            :disabled="isLoading"
            class="px-5 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl transition shadow-sm cursor-pointer"
          >
            {{ step === 'request' ? 'Получить код' : 'Подтвердить и войти' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Lock, X } from 'lucide-vue-next'

const { isAuthModalOpen, closeAuthModal, setAuthSession } = useAuth()
const { showToast } = useToast()

const isRegisterMode = ref(false)
const step = ref<'request' | 'otp'>('request')
const isLoading = ref(false)

const authForm = ref({
  fullName: '',
  identifier: '',
  code: ''
})

const quickDemoLogin = (role: 'owner' | 'accountant') => {
  const user = role === 'owner'
    ? {
        id: 'user_01',
        email: 'smirnov@center-invest.ru',
        full_name: 'Иван Смирнов',
        role: 'owner' as const,
        company_id: 'C001'
      }
    : {
        id: 'user_02',
        email: 'kovaleva@center-invest.ru',
        full_name: 'Анна Ковалева',
        role: 'accountant' as const,
        company_id: 'C001'
      }

  setAuthSession('demo_session_token_' + role, user)
  showToast(`Добро пожаловать, ${user.full_name}!`, 'success')
  closeAuthModal()
}

const handleAuthSubmit = async () => {
  if (step.value === 'request') {
    if (!authForm.value.identifier) {
      showToast('Укажите email или телефон', 'warning')
      return
    }
    step.value = 'otp'
    showToast('Код подтверждения отправлен (демо-код: 123456)', 'info')
  } else {
    // Verify OTP
    const user = {
      id: 'user_custom',
      email: authForm.value.identifier,
      full_name: authForm.value.fullName || 'Предприниматель',
      role: 'owner' as const,
      company_id: 'C001'
    }
    setAuthSession('session_token_valid', user)
    showToast(`Успешный вход в аккаунт!`, 'success')
    closeAuthModal()
    step.value = 'request'
  }
}
</script>
