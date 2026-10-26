import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export const C = {
  accent: '#0F4C5C',
  amber: '#B4530A',
  ink: '#14161A',
  muted: '#6B6F76',
  hair: '#E4E2DC',
  band: 'rgba(15, 76, 92, 0.12)',
}

/** Shared axis/text styling so every chart reads as one system. */
export const base: echarts.EChartsOption = {
  textStyle: { fontFamily: 'IBM Plex Sans, system-ui, sans-serif', color: C.muted },
  grid: { left: 56, right: 16, top: 32, bottom: 40 },
  tooltip: {
    trigger: 'axis',
    borderColor: C.hair,
    textStyle: { color: C.ink, fontSize: 12 },
    extraCssText: 'box-shadow:none;border-radius:2px;',
  },
  legend: { top: 0, left: 0, icon: 'rect', itemWidth: 14, itemHeight: 2, textStyle: { color: C.muted } },
}

export const axis = (extra: Record<string, unknown> = {}) => ({
  axisLine: { lineStyle: { color: C.hair } },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: C.hair, type: 'dashed' as const } },
  axisLabel: { color: C.muted, fontFamily: 'IBM Plex Mono, monospace', fontSize: 11 },
  ...extra,
})

export function Chart({ option, height = 320 }: { option: echarts.EChartsOption; height?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts>()

  useEffect(() => {
    chart.current = echarts.init(el.current!)
    const resize = () => chart.current?.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.current?.dispose()
    }
  }, [])

  useEffect(() => {
    chart.current?.setOption({ ...base, ...option }, true)
  }, [option])

  return <div ref={el} style={{ height, width: '100%' }} />
}
