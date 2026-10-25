<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div>
        <h2 class="text-xl font-black text-slate-900 font-display tracking-tight">Личный кабинет предпринимателя</h2>
        <p class="text-xs text-slate-500">Управление финансами, регулярными платежами, внешними интеграциями и налогами</p>
      </div>
      <button
        v-if="currentUser"
        @click="logout"
        class="flex items-center space-x-1.5 text-xs text-red-600 hover:text-red-700 bg-red-50 hover:bg-red-100 font-bold px-3 py-2 rounded-xl transition shadow-sm cursor-pointer"
      >
        <LogOut class="w-4 h-4" />
        <span>Выйти из аккаунта</span>
      </button>
    </div>

    <!-- Cabinet Sub-Navigation Bar -->
    <div class="flex items-center space-x-1.5 overflow-x-auto hide-scrollbar p-1.5 bg-slate-100 rounded-2xl text-xs font-bold border border-slate-200">
      <button
        v-for="sub in subtabs"
        :key="sub.id"
        @click="activeSubtab = sub.id"
        :class="[
          activeSubtab === sub.id ? 'cab-sub-active' : 'cab-sub-inactive',
          'px-3.5 py-2 rounded-xl transition flex items-center space-x-1.5 cursor-pointer'
        ]"
      >
        <component :is="sub.icon" class="w-4 h-4" />
        <span>{{ sub.label }}</span>
      </button>
    </div>

    <!-- SUBTAB 1: Profile & Statements -->
    <div v-if="activeSubtab === 'profile'" class="space-y-5">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        
        <!-- Requisites card -->
        <div class="lg:col-span-2 bg-white rounded-2xl p-6 card-shadow border border-slate-100 space-y-4">
          <div class="flex items-center justify-between pb-3 border-b border-slate-100">
            <div class="flex items-center space-x-2.5">
              <div class="w-8 h-8 rounded-xl bg-ci-100 text-ci-800 flex items-center justify-center font-bold">
                <Building2 class="w-4 h-4" />
              </div>
              <div>
                <h3 class="text-sm font-black text-slate-900">Реквизиты и система налогообложения</h3>
                <p class="text-[10px] text-slate-400">Настройки расчетного счета и налогового режима</p>
              </div>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div>
              <label class="block font-bold text-slate-700 mb-1">Наименование бизнеса / ФИО ИП:</label>
              <input
                type="text"
                v-model="profileForm.name"
                class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
              >
            </div>
            <div>
              <label class="block font-bold text-slate-700 mb-1">ИНН:</label>
              <input
                type="text"
                v-model="profileForm.inn"
                class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500 font-mono"
              >
            </div>
            <div>
              <label class="block font-bold text-slate-700 mb-1">ОГРН / ОГРНИП:</label>
              <input
                type="text"
                v-model="profileForm.ogrn"
                placeholder="321619600012345"
                class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500 font-mono"
              >
            </div>
            <div>
              <label class="block font-bold text-slate-700 mb-1">Система налогообложения:</label>
              <select
                v-model="profileForm.tax_system"
                class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
              >
                <option value="УСН «Доходы» 6%">УСН «Доходы» 6%</option>
                <option value="УСН «Доходы минус расходы» 15%">УСН «Доходы минус расходы» 15%</option>
                <option value="ОСНО (Общая с НДС 20%)">ОСНО (Общая с НДС 20%)</option>
                <option value="Патент (ПСН)">Патент (ПСН)</option>
              </select>
            </div>
            <div class="sm:col-span-2">
              <label class="block font-bold text-slate-700 mb-1">ФИО руководителя / Предпринимателя:</label>
              <input
                type="text"
                v-model="profileForm.director_name"
                class="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-bold text-slate-900 focus:ring-2 focus:ring-ci-500"
              >
            </div>
          </div>

          <div class="pt-3 border-t border-slate-100 flex justify-end">
            <button
              @click="saveProfile"
              class="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs rounded-xl transition shadow-sm cursor-pointer"
            >
              Сохранить изменения
            </button>
          </div>
        </div>

        <!-- Import / Upload statement card -->
        <div class="bg-white rounded-2xl p-6 card-shadow border border-slate-100 space-y-4">
          <div class="flex items-center space-x-2.5 pb-3 border-b border-slate-100">
            <div class="w-8 h-8 rounded-xl bg-blue-100 text-blue-800 flex items-center justify-center font-bold">
              <ArrowDownToLine class="w-4 h-4" />
            </div>
            <div>
              <h3 class="text-sm font-black text-slate-900">Импорт транзакций</h3>
              <p class="text-[10px] text-slate-400">Загрузка банковских выписок 1C / CSV</p>
            </div>
          </div>

          <div class="p-4 border-2 border-dashed border-slate-200 hover:border-emerald-500 rounded-xl bg-slate-50 text-center transition">
            <input
              type="file"
              ref="fileInput"
              accept=".csv,.txt,.pdf"
              class="hidden"
              @change="onFileSelected"
            >
            <button
              type="button"
              @click="triggerFileInput"
              class="bg-white border border-slate-200 hover:bg-slate-100 text-slate-800 font-bold text-xs px-3.5 py-2 rounded-lg transition shadow-sm cursor-pointer"
            >
              Выбрать файл выписки
            </button>
            <div v-if="selectedFileName" class="mt-2 text-emerald-700 font-bold text-xs truncate">
              {{ selectedFileName }}
            </div>
            <p class="text-[10px] text-slate-400 mt-1">Поддерживаются CSV, 1CClientBankExchange (TXT), PDF</p>
          </div>

          <button
            @click="handleUpload"
            :disabled="!selectedFile || isUploading"
            class="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 text-white font-bold text-xs py-2.5 rounded-xl transition shadow-sm cursor-pointer"
          >
            {{ isUploading ? 'Загрузка и парсинг...' : 'Загрузить и проанализировать' }}
          </button>
        </div>

      </div>
    </div>

    <!-- SUBTAB 2: Regular Slots -->
    <div v-else-if="activeSubtab === 'slots'" class="bg-white rounded-2xl p-6 card-shadow border border-slate-100 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-100">
        <div>
          <h3 class="text-base font-black text-slate-900">Регулярные слоты обязательств</h3>
          <p class="text-xs text-slate-400">Автодетектированные и плановые циклические платежи</p>
        </div>
        <button
          @click="showAddSlotModal = true"
          class="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-1.5 rounded-xl transition flex items-center space-x-1.5 shadow-sm cursor-pointer"
        >
          <Plus class="w-3.5 h-3.5" />
          <span>+ Добавить слот</span>
        </button>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div
          v-for="(slot, idx) in slots"
          :key="idx"
          class="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-2"
        >
          <div class="flex items-center justify-between">
            <span class="font-extrabold text-xs text-slate-900">{{ slot.title }}</span>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
              {{ slot.frequency }}
            </span>
          </div>
          <div class="font-black text-sm text-slate-900">{{ formatMoney(slot.amount) }} ₽</div>
          <div class="text-[11px] text-slate-400 flex items-center justify-between">
            <span>{{ slot.dayInfo }}</span>
            <span class="text-emerald-600 font-semibold">Активен</span>
          </div>
        </div>
      </div>
    </div>

    <!-- SUBTAB 3: Analytics / DDS -->
    <div v-else-if="activeSubtab === 'analytics'" class="bg-white rounded-2xl p-6 card-shadow border border-slate-100 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-100">
        <div>
          <h3 class="text-base font-black text-slate-900">Аналитика ДДС (Движение Денежных Средств)</h3>
          <p class="text-xs text-slate-400">Структура денежных потоков по операционной, финансовой и инвестиционной деятельности</p>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
        <div class="p-4 bg-emerald-50 rounded-xl border border-emerald-200">
          <span class="text-[10px] uppercase font-bold text-emerald-700 block mb-0.5">Входящий поток (Поступления)</span>
          <div class="text-lg font-black text-emerald-800 font-display">+3 420 500 ₽</div>
        </div>
        <div class="p-4 bg-slate-50 rounded-xl border border-slate-200">
          <span class="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Исходящий поток (Списания)</span>
          <div class="text-lg font-black text-slate-900 font-display">-3 180 200 ₽</div>
        </div>
        <div class="p-4 bg-emerald-100/60 rounded-xl border border-emerald-300">
          <span class="text-[10px] uppercase font-bold text-emerald-800 block mb-0.5">Чистый операционный поток (Net Flow)</span>
          <div class="text-lg font-black text-emerald-900 font-display">+240 300 ₽</div>
        </div>
      </div>
    </div>

    <!-- SUBTAB 4: Integrations -->
    <div v-else-if="activeSubtab === 'integrations'" class="space-y-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100 flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-xl bg-amber-100 text-amber-800 flex items-center justify-center font-black">
              1С
            </div>
            <div>
              <div class="font-extrabold text-sm text-slate-900">1С:Предприятие 8.3 / Бухгалтерия</div>
              <div class="text-xs text-slate-400">Прямой обмен платежными поручениями</div>
            </div>
          </div>
          <span class="px-2.5 py-1 bg-emerald-100 text-emerald-800 rounded-lg text-xs font-bold">Подключено</span>
        </div>

        <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100 flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-xl bg-blue-100 text-blue-800 flex items-center justify-center font-black">
              ФНС
            </div>
            <div>
              <div class="font-extrabold text-sm text-slate-900">API ФНС России (nalog.ru)</div>
              <div class="text-xs text-slate-400">Проверка блокировок по ст. 76 НК РФ</div>
            </div>
          </div>
          <span class="px-2.5 py-1 bg-emerald-100 text-emerald-800 rounded-lg text-xs font-bold">Активно</span>
        </div>
      </div>
    </div>

    <!-- SUBTAB 5: USN Tax Declaration КНД 1152017 -->
    <div v-else-if="activeSubtab === 'taxes'" class="space-y-4">
      <div class="bg-white rounded-2xl p-5 card-shadow border border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div class="flex items-center space-x-2">
            <span class="px-2.5 py-1 rounded-lg bg-purple-100 text-purple-900 font-extrabold text-xs">
              КНД 1152017
            </span>
            <h3 class="text-base font-black text-slate-900 font-display">Налоговая декларация по УСН</h3>
          </div>
          <p class="text-xs text-slate-500 mt-1">
            Официальный машиночитаемый бланк декларации по форме ФНС России с автозаполнением авансовых платежей
          </p>
        </div>
        <div class="flex items-center space-x-2">
          <button
            @click="downloadTaxDeclarationPDF"
            class="bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold text-xs px-4 py-2.5 rounded-xl transition flex items-center space-x-2 shadow-sm cursor-pointer"
          >
            <Download class="w-4 h-4" />
            <span>Скачать официальный PDF</span>
          </button>
        </div>
      </div>

      <!-- A4 Declaration Preview Page -->
      <div class="overflow-x-auto p-4 bg-slate-200 rounded-2xl flex justify-center">
        <div class="fns-a4-page shadow-2xl relative text-black text-xs font-mono">
          <div class="fns-corner-sq top-3 left-3"></div>
          <div class="fns-corner-sq top-3 right-3"></div>
          <div class="fns-corner-sq bottom-3 left-3"></div>
          <div class="fns-corner-sq bottom-3 right-3"></div>

          <div class="text-center pb-4 border-b border-black">
            <div class="text-sm font-black uppercase">Налоговая декларация по налогу, уплачиваемому в связи с применением УСН</div>
            <div class="text-[10px] text-slate-600">Форма по КНД 1152017</div>
          </div>

          <div class="pt-4 space-y-3">
            <div>
              <span class="text-[10px] font-bold block text-slate-600">ИНН:</span>
              <div class="flex flex-wrap">
                <span v-for="(char, i) in (activeCompany?.inn || '6164000000').split('')" :key="i" class="fns-cell">
                  {{ char }}
                </span>
              </div>
            </div>

            <div>
              <span class="text-[10px] font-bold block text-slate-600">Налогоплательщик:</span>
              <div class="font-bold border border-black p-2 bg-slate-50">
                {{ activeCompany?.name || 'ИП Иванов Иван Иванович' }}
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3 pt-2">
              <div class="p-3 border border-black bg-slate-50">
                <span class="text-[10px] font-bold block text-slate-600">Объект налогообложения:</span>
                <span class="font-bold">1 - Доходы (6%)</span>
              </div>
              <div class="p-3 border border-black bg-slate-50">
                <span class="text-[10px] font-bold block text-slate-600">Налоговый период (код):</span>
                <span class="font-bold">34 (Календарный год)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Building2,
  Repeat,
  BarChart3,
  Layers,
  FileSignature,
  ArrowDownToLine,
  Download,
  Plus,
  LogOut
} from 'lucide-vue-next'
import { formatMoney } from '~/utils/format'

const { activeCompany, updateProfile } = useCompany()
const { currentUser, logout } = useAuth()
const { uploadStatement } = useOperations()
const { showToast } = useToast()

const activeSubtab = ref('profile')
const showAddSlotModal = ref(false)
const isUploading = ref(false)
const selectedFile = ref<File | null>(null)
const selectedFileName = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const profileForm = ref({
  name: activeCompany.value?.name || '',
  inn: activeCompany.value?.inn || '',
  ogrn: activeCompany.value?.ogrn || '',
  tax_system: activeCompany.value?.tax_system || 'УСН «Доходы» 6%',
  director_name: activeCompany.value?.director_name || ''
})

const subtabs = [
  { id: 'profile', label: 'Реквизиты и Налоги', icon: Building2 },
  { id: 'slots', label: 'Слоты и платежи', icon: Repeat },
  { id: 'analytics', label: 'ДДС аналитика', icon: BarChart3 },
  { id: 'integrations', label: '1С / ФНС интеграции', icon: Layers },
  { id: 'taxes', label: 'Декларация УСН', icon: FileSignature }
]

const slots = ref([
  { title: 'Аренда офиса и склада', amount: 150000, frequency: 'Ежемесячно', dayInfo: '5 число месяца' },
  { title: 'Зарплатный фонд (ФОТ)', amount: 480000, frequency: '2 раза в месяц', dayInfo: '10 и 25 число' },
  { title: 'Налоги и сборы (ЕНП)', amount: 95000, frequency: 'Ежеквартально', dayInfo: '28 число квартала' },
  { title: 'Логистика и доставка', amount: 65000, frequency: 'Еженедельно', dayInfo: 'Каждый понедельник' },
  { title: 'Интернет и связь', amount: 12000, frequency: 'Ежемесячно', dayInfo: '1 число месяца' }
])

const triggerFileInput = () => {
  fileInput.value?.click()
}

const onFileSelected = (e: Event) => {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    selectedFile.value = target.files[0]
    selectedFileName.value = target.files[0].name
  }
}

const handleUpload = async () => {
  if (!selectedFile.value || !activeCompany.value) return
  isUploading.value = true
  try {
    await uploadStatement(activeCompany.value.id, selectedFile.value)
    showToast('Выписка успешно загружена и проанализирована!', 'success')
    selectedFile.value = null
    selectedFileName.value = ''
  } catch (err: any) {
    showToast(err.message || 'Ошибка загрузки выписки', 'error')
  } finally {
    isUploading.value = false
  }
}

const saveProfile = async () => {
  if (!activeCompany.value) return
  try {
    await updateProfile(activeCompany.value.id, profileForm.value)
    showToast('Реквизиты успешно обновлены!', 'success')
  } catch (err: any) {
    showToast(err.message || 'Ошибка сохранения', 'error')
  }
}

const downloadTaxDeclarationPDF = () => {
  window.open(`/api/companies/${activeCompany.value?.id || 'C001'}/tax-declaration/pdf`, '_blank')
}
</script>
