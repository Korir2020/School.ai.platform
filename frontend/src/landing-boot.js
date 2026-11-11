// The public opening screen lasts at most half a second, including its fade.
export const BOOT_FADE_MS = 150;
export const BOOT_MAX_MS = 500;
export function bootDelay(elapsed, reducedMotion = false) {
  return reducedMotion ? 0 : Math.max(0, BOOT_MAX_MS - BOOT_FADE_MS - elapsed);
}