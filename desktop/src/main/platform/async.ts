/** Promise-based sleep used across the (necessarily paced) injection paths. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
