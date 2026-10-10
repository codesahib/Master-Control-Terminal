import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { useApp } from "../context";
import { compactMoney, money, shortDate } from "../lib/format";

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Colors come from the CSS tokens, so charts follow the light/dark theme.
export function useChartColors() {
  const { theme } = useApp();
  return useMemo(
    () => ({
      text: cssVar("--text-2"),
      muted: cssVar("--text-3"),
      grid: cssVar("--grid"),
      surface: cssVar("--surface"),
      tooltipBg: cssVar("--surface-3"),
      border: cssVar("--border-strong"),
      accent: cssVar("--accent"),
      series: [1, 2, 3, 4, 5, 6, 7, 8].map((index) => cssVar(`--c${index}`)),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme]
  );
}

function tooltip(colors: ReturnType<typeof useChartColors>) {
  return {
    backgroundColor: colors.tooltipBg,
    borderColor: colors.border,
    textStyle: { color: cssVar("--text"), fontFamily: "Geist, system-ui, sans-serif", fontSize: 12 },
    extraCssText: "border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,.25);",
  };
}

function Chart({ option, height, label }: { option: object; height: number; label: string }) {
  return (
    <div className="chart-box money" role="img" aria-label={label}>
      <ReactECharts option={option} notMerge style={{ height, width: "100%" }} opts={{ renderer: "svg" }} />
    </div>
  );
}

export function ValueChart({ points, height = 240 }: { points: { date: string; market: number; book: number }[]; height?: number }) {
  const colors = useChartColors();
  const option = {
    grid: { left: 8, right: 8, top: 12, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "axis",
      ...tooltip(colors),
      valueFormatter: (value: number) => money(value),
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: points.map((point) => point.date),
      axisLabel: { color: colors.muted, formatter: (value: string) => shortDate(value).replace(/, \d{4}$/, "") },
      axisLine: { lineStyle: { color: colors.grid } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: colors.muted, formatter: (value: number) => compactMoney(value) },
      splitLine: { lineStyle: { color: colors.grid } },
    },
    series: [
      {
        name: "Market value",
        type: "line",
        data: points.map((point) => point.market),
        smooth: 0.25,
        symbol: "none",
        lineStyle: { width: 2.25, color: colors.accent },
        areaStyle: { color: colors.accent, opacity: 0.12 },
      },
      {
        name: "Book value",
        type: "line",
        data: points.map((point) => point.book),
        symbol: "none",
        lineStyle: { width: 1.5, type: "dashed", color: colors.muted },
      },
    ],
  };
  return <Chart option={option} height={height} label={`Portfolio value from ${money(points[0]?.market)} to ${money(points[points.length - 1]?.market)}`} />;
}

export function Donut({ data, height = 200 }: { data: { label: string; value: number }[]; height?: number }) {
  const colors = useChartColors();
  const option = {
    tooltip: {
      trigger: "item",
      ...tooltip(colors),
      formatter: (params: { name: string; value: number; percent: number }) => `${params.name}<br/>${money(params.value)} · ${params.percent.toFixed(1)}%`,
    },
    color: colors.series,
    series: [
      {
        type: "pie",
        radius: ["62%", "86%"],
        avoidLabelOverlap: true,
        label: { show: false },
        itemStyle: { borderColor: colors.surface, borderWidth: 2 },
        data: data.map((item) => ({ name: item.label, value: Math.round(item.value * 100) / 100 })),
      },
    ],
  };
  return <Chart option={option} height={height} label={data.map((item) => `${item.label} ${money(item.value, "CAD", 0)}`).join(", ")} />;
}

export function FlowChart({ data, height = 220 }: { data: { month: string; contributions: number; investments: number }[]; height?: number }) {
  const colors = useChartColors();
  const option = {
    grid: { left: 8, right: 8, top: 12, bottom: 4, containLabel: true },
    tooltip: { trigger: "axis", ...tooltip(colors), valueFormatter: (value: number) => money(value) },
    xAxis: {
      type: "category",
      data: data.map((point) => point.month),
      axisLabel: { color: colors.muted, formatter: (value: string) => new Date(`${value}-01T00:00:00`).toLocaleDateString("en-CA", { month: "short" }) },
      axisLine: { lineStyle: { color: colors.grid } },
      axisTick: { show: false },
    },
    yAxis: { type: "value", axisLabel: { color: colors.muted, formatter: (value: number) => compactMoney(value) }, splitLine: { lineStyle: { color: colors.grid } } },
    series: [
      { name: "Contributed", type: "bar", data: data.map((point) => point.contributions), itemStyle: { color: colors.series[0], borderRadius: [4, 4, 0, 0] }, barMaxWidth: 14 },
      { name: "Invested (net)", type: "bar", data: data.map((point) => point.investments), itemStyle: { color: colors.series[1], borderRadius: [4, 4, 0, 0] }, barMaxWidth: 14 },
    ],
  };
  return <Chart option={option} height={height} label="Monthly contributions and net investments" />;
}
