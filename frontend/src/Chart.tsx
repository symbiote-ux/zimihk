import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, MarkAreaComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

echarts.use([BarChart, LineChart, DataZoomComponent, GridComponent, LegendComponent, MarkAreaComponent, TooltipComponent, CanvasRenderer])

export const COLORS = {
  accent: '#0F4C5C',
  amber: '#B4530A',
  ink: '#14161A',
  muted: '#6B6F76',
  hair: '#E4E2DC',
  band: 'rgba(15, 76, 92, 0.12)',
}

/** Shared axis/text styling so every chart reads as one system. */
export const base: EChartsOption = {
  textStyle: { fontFamily: 'IBM Plex Sans, system-ui, sans-serif', color: COLORS.muted },
  grid: { left: 56, right: 16, top: 32, bottom: 40 },
  tooltip: {
    trigger: 'axis',
    borderColor: COLORS.hair,
    textStyle: { color: COLORS.ink, fontSize: 12 },
    extraCssText: 'box-shadow:none;border-radius:2px;',
  },
  legend: { top: 0, left: 0, icon: 'rect', itemWidth: 14, itemHeight: 2, textStyle: { color: COLORS.muted } },
}

export const axis = (extra: Record<string, unknown> = {}) => ({
  axisLine: { lineStyle: { color: COLORS.hair } },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: COLORS.hair, type: 'dashed' as const } },
  axisLabel: { color: COLORS.muted, fontFamily: 'IBM Plex Mono, monospace', fontSize: 11 },
  ...extra,
})

export function Chart({ option, height = 320 }: { option: EChartsOption; height?: number }) {
  const container = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts>()

  useEffect(() => {
    chart.current = echarts.init(container.current!)
    const resize = () => chart.current?.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.current?.dispose()
    }
  }, [])

  useEffect(() => {
    chart.current?.setOption({ ...base, ...option, legend: { ...(base.legend as object), ...(option.legend as object) } }, true)
  }, [option])

  return <div ref={container} style={{ height, width: '100%' }} />
}
