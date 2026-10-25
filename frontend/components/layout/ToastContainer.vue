<template>
  <div class="fixed bottom-5 right-5 z-50 flex flex-col space-y-2 pointer-events-none max-w-sm w-full">
    <transition-group
      enter-active-class="transform ease-out duration-300 transition"
      enter-from-class="translate-y-2 opacity-0 sm:translate-y-0 sm:translate-x-2"
      enter-to-class="translate-y-0 opacity-100 sm:translate-x-0"
      leave-active-class="transition ease-in duration-200"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="pointer-events-auto flex items-center justify-between p-3.5 rounded-2xl shadow-xl border text-xs font-bold leading-snug backdrop-blur-md"
        :class="getToastClass(toast.type)"
      >
        <div class="flex items-center space-x-2.5">
          <component :is="getToastIcon(toast.type)" class="w-4 h-4 shrink-0" />
          <span>{{ toast.message }}</span>
        </div>
        <button
          @click="removeToast(toast.id)"
          class="ml-3 p-1 rounded-lg hover:bg-black/10 transition cursor-pointer"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-vue-next'

const { toasts, removeToast } = useToast()

const getToastClass = (type: string) => {
  switch (type) {
    case 'success':
      return 'bg-emerald-900/90 text-white border-emerald-700/50 shadow-emerald-950/20'
    case 'error':
      return 'bg-red-900/90 text-white border-red-700/50 shadow-red-950/20'
    case 'warning':
      return 'bg-amber-900/90 text-white border-amber-700/50 shadow-amber-950/20'
    default:
      return 'bg-slate-900/90 text-white border-slate-700/50 shadow-slate-950/20'
  }
}

const getToastIcon = (type: string) => {
  switch (type) {
    case 'success':
      return CheckCircle2
    case 'error':
      return AlertCircle
    case 'warning':
      return AlertTriangle
    default:
      return Info
  }
}
</script>
