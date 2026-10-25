<template>
  <div class="relative w-full h-full min-h-[300px]">
    <canvas ref="chartCanvas"></canvas>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip
} from 'chart.js'
import { formatDate, formatMoney } from '~/utils/format'
import type { ScenarioComparisonPoint } from '~/composables/useScenarios'

Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip
)

const props = defineProps<{
  points: ScenarioComparisonPoint[]
}>()

const chartCanvas = ref<HTMLCanvasElement | null>(null)
let chartInstance: Chart | null = null

const renderChart = () => {
  if (!chartCanvas.value) return
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }

  const points = props.points || []
  if (points.length === 0) return

  const labels = points.map(p => formatDate(p.date))
  const baseData = points.map(p => p.baseline_p50)
  const scenData = points.map(p => p.scenario_p50)
  const zeroLine = points.map(() => 0)
  const hasNegative = scenData.some(v => v < 0)

  const ctx = chartCanvas.value.getContext('2d')
  if (!ctx) return

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Базовый прогноз (P50)',
          data: baseData,
          borderColor: '#64748B',
          borderWidth: 2,
          borderDash: [5, 4],
          pointRadius: 0,
          fill: false,
          tension: 0.15
        },
        {
          label: 'Стресс-сценарий (P50)',
          data: scenData,
          borderColor: hasNegative ? '#EF4444' : '#059669',
          borderWidth: 2.5,
          pointRadius: 0,
          fill: false,
          tension: 0.15
        },
        {
          label: 'Уровень кассового разрыва (0 ₽)',
          data: zeroLine,
          borderColor: '#EF4444',
          borderWidth: 1.5,
          borderDash: [3, 3],
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0F172A',
          titleFont: { family: 'Manrope', size: 11, weight: 'bold' },
          bodyFont: { family: 'Manrope', size: 11 },
          padding: 8,
          cornerRadius: 8,
          callbacks: {
            label: function(context: any) {
              const val = formatMoney(context.parsed.y)
              return ` ${context.dataset.label}: ${val} ₽`
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: 'Manrope', size: 10 }, color: '#94A3B8', maxTicksLimit: 8 }
        },
        y: {
          grid: { color: '#F1F5F9' },
          ticks: {
            font: { family: 'Manrope', size: 10 },
            color: '#94A3B8',
            callback: function(value: any) {
              const num = Number(value)
              if (Math.abs(num) >= 1000000) return (num / 1000000).toFixed(1) + ' млн ₽'
              if (Math.abs(num) >= 1000) return (num / 1000).toFixed(0) + ' тыс ₽'
              return num + ' ₽'
            }
          }
        }
      }
    }
  })
}

onMounted(() => {
  renderChart()
})

onBeforeUnmount(() => {
  if (chartInstance) {
    chartInstance.destroy()
  }
})

watch(() => props.points, () => {
  renderChart()
}, { deep: true })
</script>
