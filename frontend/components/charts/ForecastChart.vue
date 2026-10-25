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
  Tooltip,
  Filler
} from 'chart.js'
import { formatDate, formatMoney } from '~/utils/format'

Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Tooltip,
  Filler
)

const props = defineProps<{
  forecastData: any
  modelType: string
  debugMode?: boolean
}>()

const chartCanvas = ref<HTMLCanvasElement | null>(null)
let chartInstance: Chart | null = null

const renderChart = () => {
  if (!chartCanvas.value) return
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }

  const fd = props.forecastData
  if (!fd) return

  // Days can come as fd.days: [{ date, p10, p50, p90 }] or fd.dates: [] + fd.p50: []
  let labels: string[] = []
  let p50Data: number[] = []
  let p10Data: number[] = []
  let p90Data: number[] = []

  if (Array.isArray(fd.days) && fd.days.length > 0) {
    labels = fd.days.map((d: any) => formatDate(d.date))
    p50Data = fd.days.map((d: any) => d.p50)
    p10Data = fd.days.map((d: any) => d.p10)
    p90Data = fd.days.map((d: any) => d.p90)
  } else if (Array.isArray(fd.dates) && fd.dates.length > 0) {
    labels = fd.dates.map((d: string) => formatDate(d))
    p50Data = fd.p50 || []
    p10Data = fd.p10 || []
    p90Data = fd.p90 || []
  }

  const zeroLine = labels.map(() => 0)

  const datasets: any[] = [
    {
      label: 'Ожидаемый остаток',
      data: p50Data,
      borderColor: '#059669',
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 5,
      tension: 0.25,
      order: 1
    },
    {
      label: 'Оптимистичный (P90)',
      data: p90Data,
      borderColor: 'rgba(16, 185, 129, 0.2)',
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
      tension: 0.3,
      order: 2
    },
    {
      label: 'Пессимистичный (P10)',
      data: p10Data,
      borderColor: 'rgba(16, 185, 129, 0.2)',
      borderWidth: 1,
      pointRadius: 0,
      backgroundColor: 'rgba(16, 185, 129, 0.08)',
      fill: '-1',
      tension: 0.3,
      order: 3
    },
    {
      label: 'Граница разрыва',
      data: zeroLine,
      borderColor: '#EF4444',
      borderWidth: 1.5,
      borderDash: [4, 4],
      pointRadius: 0,
      fill: false,
      order: 0
    }
  ]

  // Show Monte Carlo sample paths if MC or debugMode
  const isMC = (fd.model_version && fd.model_version.startsWith('monte-carlo')) || props.modelType === 'monte-carlo'
  if ((isMC || props.debugMode) && fd.sample_paths && Array.isArray(fd.sample_paths) && fd.sample_paths.length > 0) {
    const pathColors = [
      'rgba(239, 68, 68, 0.35)',    // P5  - red
      'rgba(245, 158, 11, 0.35)',   // P25 - amber
      'rgba(99, 102, 241, 0.35)',   // P50 - indigo
      'rgba(34, 197, 94, 0.35)',    // P75 - green
      'rgba(59, 130, 246, 0.35)',   // P95 - blue
    ]
    const pathLabels = fd.simulation_meta?.sample_path_labels || ['P5', 'P25', 'P50', 'P75', 'P95']

    fd.sample_paths.forEach((path: number[], idx: number) => {
      datasets.push({
        label: `MC: ${pathLabels[idx] || 'Траектория ' + (idx + 1)}`,
        data: path,
        borderColor: pathColors[idx % pathColors.length],
        borderWidth: 1.2,
        borderDash: [3, 3],
        pointRadius: 0,
        fill: false,
        tension: 0.2,
        order: 10 + idx
      })
    })
  }

  const ctx = chartCanvas.value.getContext('2d')
  if (!ctx) return

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets
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

watch(() => [props.forecastData, props.modelType, props.debugMode], () => {
  renderChart()
}, { deep: true })
</script>
