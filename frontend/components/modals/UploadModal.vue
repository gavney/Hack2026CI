<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4"
  >
    <div class="bg-white rounded-3xl max-w-lg w-full p-6 card-shadow border border-slate-100 space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-slate-100">
        <div class="flex items-center space-x-2">
          <div class="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold">
            <UploadCloud class="w-4 h-4" />
          </div>
          <div>
            <h3 class="text-sm font-black text-slate-900">Загрузка банковской выписки</h3>
            <p class="text-[10px] text-slate-400">Форматы 1CClientBankExchange (.txt), CSV, PDF</p>
          </div>
        </div>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600 cursor-pointer">
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Drag & Drop Zone -->
      <div
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="onDrop"
        class="p-6 border-2 border-dashed rounded-2xl text-center transition cursor-pointer"
        :class="isDragging ? 'border-emerald-500 bg-emerald-50/50' : 'border-slate-200 bg-slate-50 hover:border-emerald-400'"
        @click="triggerFileInput"
      >
        <input
          type="file"
          ref="fileInput"
          accept=".csv,.txt,.pdf"
          class="hidden"
          @change="onFileSelected"
        >
        <div class="w-10 h-10 rounded-full bg-white shadow-xs flex items-center justify-center mx-auto mb-2 text-emerald-600">
          <FileText class="w-5 h-5" />
        </div>
        <div class="font-extrabold text-xs text-slate-900">
          {{ selectedFileName || 'Перетащите файл выписки сюда или нажмите для выбора' }}
        </div>
        <p class="text-[10px] text-slate-400 mt-1">
          Размер файла до 50 МБ. Поддерживаются кодировки Windows-1251 и UTF-8
        </p>
      </div>

      <!-- Progress bar if uploading -->
      <div v-if="isUploading" class="space-y-1.5">
        <div class="flex justify-between text-[11px] font-bold text-slate-700">
          <span>{{ uploadStepLabel }}</span>
          <span>{{ uploadProgress }}%</span>
        </div>
        <div class="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
          <div
            class="bg-emerald-600 h-full transition-all duration-300"
            :style="{ width: `${uploadProgress}%` }"
          ></div>
        </div>
      </div>

      <!-- 1-Click Quick Demo Statement Loaders -->
      <div class="p-3 bg-slate-50 rounded-xl space-y-2">
        <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Быстрый тест в 1 клик:</span>
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            @click="loadDemo('C001')"
            class="bg-white hover:bg-emerald-50 text-emerald-900 border border-emerald-200 font-bold py-1.5 px-3 rounded-lg text-xs transition shadow-2xs cursor-pointer"
          >
            Демо-выписка C001
          </button>
          <button
            type="button"
            @click="loadDemo('C004')"
            class="bg-white hover:bg-red-50 text-red-900 border border-red-200 font-bold py-1.5 px-3 rounded-lg text-xs transition shadow-2xs cursor-pointer"
          >
            Демо-выписка C004 (Разрыв)
          </button>
        </div>
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
          type="button"
          @click="startUpload"
          :disabled="!selectedFile || isUploading"
          class="px-5 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 text-white rounded-xl transition shadow-sm cursor-pointer"
        >
          {{ isUploading ? 'Обработка...' : 'Загрузить и проанализировать' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { UploadCloud, FileText, X } from 'lucide-vue-next'

const props = defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits(['close', 'uploaded'])

const { activeCompanyId, setCompany } = useCompany()
const { uploadStatement } = useOperations()
const { fetchForecast } = useForecast()
const { showToast } = useToast()

const isDragging = ref(false)
const isUploading = ref(false)
const selectedFile = ref<File | null>(null)
const selectedFileName = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const uploadProgress = ref(0)
const uploadStepLabel = ref('Загрузка файла...')

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

const onDrop = (e: DragEvent) => {
  isDragging.value = false
  if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
    selectedFile.value = e.dataTransfer.files[0]
    selectedFileName.value = e.dataTransfer.files[0].name
  }
}

const startUpload = async () => {
  if (!selectedFile.value || !activeCompanyId.value) return
  isUploading.value = true
  uploadProgress.value = 25
  uploadStepLabel.value = 'Загрузка файла на сервер...'

  try {
    setTimeout(() => {
      uploadProgress.value = 60
      uploadStepLabel.value = 'Парсинг 1C и AI-разметка категорий...'
    }, 400)

    await uploadStatement(activeCompanyId.value, selectedFile.value)
    uploadProgress.value = 100
    uploadStepLabel.value = 'Прогноз обновлен!'

    showToast('Выписка успешно загружена и проанализирована!', 'success')
    await fetchForecast(activeCompanyId.value)
    emit('uploaded')
    emit('close')
  } catch (err: any) {
    showToast(err.message || 'Ошибка загрузки выписки', 'error')
  } finally {
    isUploading.value = false
    uploadProgress.value = 0
  }
}

const loadDemo = async (companyId: string) => {
  setCompany(companyId)
  await fetchForecast(companyId)
  showToast(`Переключено на демонстрационную модель ${companyId}`, 'info')
  emit('close')
}
</script>
