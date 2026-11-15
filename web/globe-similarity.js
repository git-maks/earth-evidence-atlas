"use strict";

function findSimilarWindows(grid, bbox, tolerance, limit) {
  const { lat, lon, slope } = grid;
  if (lat.length < 2 || lon.length < 2) return null;

  // Use the selected grid centres, with the nearest row or column for boxes finer than the grid.
  const axisWindow = (axis, lo, hi) => {
    const first = axis.findIndex((value) => value >= lo);
    if (first >= 0 && axis[first] <= hi) {
      const pastEnd = axis.findIndex((value) => value > hi);
      return [first, pastEnd < 0 ? axis.length : pastEnd];
    }
    const center = (lo + hi) / 2;
    const nearest = axis.reduce((best, value, i) => Math.abs(value - center) < Math.abs(axis[best] - center) ? i : best, 0);
    return [nearest, nearest + 1];
  };
  const [west, south, east, north] = bbox;
  const [row0, row1] = axisWindow(lat, south, north);
  const [col0, col1] = axisWindow(lon, west, east);
  const height = row1 - row0, width = col1 - col0;

  // Summed-area tables give the weighted trend and coverage of a window in constant time.
  const stride = lon.length + 1;
  const valid = new Float64Array((lat.length + 1) * stride);
  const trends = new Float64Array(valid.length);
  const rowWeights = new Float64Array(lat.length + 1);
  lat.forEach((latitude, y) => {
    const weight = Math.cos(latitude * Math.PI / 180);
    rowWeights[y + 1] = rowWeights[y] + weight;
    let rowValid = 0, rowTrend = 0;
    slope[y].forEach((trend, x) => {
      if (Number.isFinite(trend)) {
        rowValid += weight;
        rowTrend += trend * weight;
      }
      const above = y * stride + x + 1;
      valid[above + stride] = valid[above] + rowValid;
      trends[above + stride] = trends[above] + rowTrend;
    });
  });
  const sum = (table, y, x) => {
    const top = y * stride + x, bottom = top + height * stride;
    return (table[bottom + width] - table[bottom]) - (table[top + width] - table[top]);
  };
  const windowTrend = (y, x) => {
    const weight = sum(valid, y, x);
    const coverage = weight / ((rowWeights[y + height] - rowWeights[y]) * width);
    if (weight <= 0 || coverage + 1e-10 < 0.7) return null;
    return { trend: sum(trends, y, x) / weight, coverage };
  };
  const reference = windowTrend(row0, col0);
  if (!reference) return null;

  const overlaps = (a, b) => Math.abs(a.y - b.y) < height && Math.abs(a.x - b.x) < width;
  const origin = { y: row0, x: col0 };
  const candidates = [];
  for (let y = 0; y <= lat.length - height; y++) {
    for (let x = 0; x <= lon.length - width; x++) {
      if (overlaps({ y, x }, origin)) continue;
      const match = windowTrend(y, x);
      if (!match || match.trend * reference.trend < 0) continue;
      const difference = Math.abs(match.trend - reference.trend);
      if (difference <= tolerance + 1e-10) candidates.push({ ...match, difference, y, x });
    }
  }
  candidates.sort((a, b) => a.difference - b.difference || b.coverage - a.coverage);
  const selected = [];
  for (const candidate of candidates) {
    if (selected.some((match) => overlaps(match, candidate))) continue;
    selected.push(candidate);
    if (selected.length >= limit) break;
  }

  const dlat = (lat[1] - lat[0]) / 2, dlon = (lon[1] - lon[0]) / 2;
  const rounded = (value) => Number(value.toFixed(6));
  return {
    reference: reference.trend, cells: width * height,
    matches: selected.map(({ x, y, trend, difference }) => ({
      trend, difference,
      bbox: [Math.max(-180, lon[x] - dlon), Math.max(-90, lat[y] - dlat),
        Math.min(180, lon[x + width - 1] + dlon), Math.min(90, lat[y + height - 1] + dlat)].map(rounded),
    })),
  };
}
