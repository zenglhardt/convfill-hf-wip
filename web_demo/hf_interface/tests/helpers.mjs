export async function waitFor(predicate, { timeout = 10_000, interval = 25 } = {}) {
  const deadline = Date.now() + timeout;
  let value;
  while (Date.now() < deadline) {
    value = await predicate();
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
  throw new Error(
    `condition not met within ${timeout} ms; last value: ${JSON.stringify(value)}`,
  );
}
