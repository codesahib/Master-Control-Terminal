import ReactECharts from "echarts-for-react";
import type { ReactNode } from "react";
import { DistributionPoint } from "../types";

interface Props {
  title: string;
  data: DistributionPoint[];
  actions?: ReactNode;
}

export function DistributionChart({ title, data, actions }: Props) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  const valueByName = Object.fromEntries(data.map((item) => [item.label, item.value]));

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      formatter: (params: { name: string; value: number; percent: number }) =>
        `${params.name}<br/>${params.percent.toFixed(1)}% ($${params.value.toLocaleString()})`,
    },
    legend: {
      orient: "vertical",
      right: 16,
      top: "middle",
      textStyle: { color: "#cbd5f5" },
      type: "scroll",
      formatter: (name: string) => {
        const value = valueByName[name] ?? 0;
        const percent = total > 0 ? (value / total) * 100 : 0;
        return `${name}  ${percent.toFixed(1)}%  ($${value.toLocaleString()})`;
      },
    },
    media: [
      {
        query: { maxWidth: 700 },
        option: {
          legend: { orient: "horizontal", left: 0, right: 0, top: "bottom" },
          series: [{ center: ["50%", "42%"], radius: ["28%", "52%"], label: { show: false } }],
        },
      },
    ],
    series: [
      {
        type: "pie",
        center: ["30%", "52%"],
        radius: ["28%", "58%"],
        itemStyle: { borderRadius: 8, borderColor: "#0b1020", borderWidth: 2 },
        label: {
          show: true,
          color: "#e6ecff",
          formatter: (params: { value: number; percent: number }) =>
            `${params.percent.toFixed(1)}%\n$${params.value.toLocaleString()}`,
        },
        data: data.map((d) => ({ name: d.label, value: d.value })),
      },
    ],
  };

  return (
    <div className="panel chart">
      <div className="chart-header">
        <h3>{title}</h3>
        {actions}
      </div>
      {data.length === 0 ? (
        <div className="chart-empty">No chart data for the current filters.</div>
      ) : (
        <ReactECharts className="chart-canvas" option={option} />
      )}
    </div>
  );
}
