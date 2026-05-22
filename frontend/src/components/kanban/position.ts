export const POSITION_STEP = 1000;

export function computePosition(
  sorted: { position: number }[],
  toIndex: number,
): number {
  if (sorted.length === 0) return POSITION_STEP;
  if (toIndex <= 0) return sorted[0].position - POSITION_STEP;
  if (toIndex >= sorted.length) return sorted[sorted.length - 1].position + POSITION_STEP;
  return (sorted[toIndex - 1].position + sorted[toIndex].position) / 2;
}
