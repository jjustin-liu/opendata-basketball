export function ballRiskColor(risk) {
  const t = Number.isFinite(risk) ? Math.max(0, Math.min(1, (risk - .06) / .09)) : 0;
  const gold = [242, 180, 64], red = [239, 57, 57];
  return `rgb(${gold.map((channel, i) => Math.round(channel + (red[i] - channel) * t)).join(',')})`;
}
