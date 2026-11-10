export function circleVisibleFraction(particle, width, height, samples = 240) {
  if (particle.r <= 0) return 0;
  if (
    particle.x - particle.r >= 0 &&
    particle.x + particle.r <= width &&
    particle.y - particle.r >= 0 &&
    particle.y + particle.r <= height
  ) {
    return 1;
  }

  const xMin = Math.max(0, particle.x - particle.r);
  const xMax = Math.min(width, particle.x + particle.r);
  if (
    xMin >= xMax ||
    particle.y + particle.r <= 0 ||
    particle.y - particle.r >= height
  ) {
    return 0;
  }

  const dx = (xMax - xMin) / samples;
  let visibleArea = 0;
  for (let idx = 0; idx < samples; idx += 1) {
    const x = xMin + (idx + 0.5) * dx;
    const halfHeight = Math.sqrt(
      Math.max(0, particle.r * particle.r - (x - particle.x) ** 2),
    );
    const yMin = Math.max(0, particle.y - halfHeight);
    const yMax = Math.min(height, particle.y + halfHeight);
    visibleArea += Math.max(0, yMax - yMin) * dx;
  }
  return Math.min(1, Math.max(0, visibleArea / (Math.PI * particle.r * particle.r)));
}

export function summarizeDiameters(inputValues) {
  const values = inputValues.filter((value) => value > 0).sort((a, b) => a - b);
  if (!values.length) return null;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const mid = Math.floor(values.length / 2);
  const median = values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
  return {
    count: values.length,
    mean,
    median,
    min: values[0],
    max: values[values.length - 1],
  };
}
