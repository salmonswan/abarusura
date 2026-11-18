export function readPaused(storage: Pick<Storage, 'getItem'>): boolean {
  try {
    return storage.getItem('abar-paused') === '1'
  } catch {
    return false
  }
}

export function writePaused(storage: Pick<Storage, 'setItem'>, paused: boolean): void {
  try {
    storage.setItem('abar-paused', paused ? '1' : '0')
  } catch {
    // The control still works when browser storage is blocked.
  }
}
