export type Slideshow = {
  readonly index: number
  play: () => void
  pause: () => void
}

type SlideshowOptions<Timer> = {
  count: number
  ms: number
  onShow: (index: number) => void
  now: () => number
  setTimer: (callback: () => void, delay: number) => Timer
  clearTimer: (timer: Timer) => void
}

export function createSlideshow<Timer>({ count, ms, onShow, now, setTimer, clearTimer }: SlideshowOptions<Timer>): Slideshow {
  let index = 0
  let remaining = ms
  let deadline = 0
  let timer: Timer | undefined

  function schedule() {
    deadline = now() + remaining
    timer = setTimer(() => {
      timer = undefined
      index = (index + 1) % count
      remaining = ms
      schedule()
      onShow(index)
    }, remaining)
  }

  return {
    get index() { return index },
    play() {
      if (timer === undefined) schedule()
    },
    pause() {
      if (timer === undefined) return
      remaining = Math.max(0, deadline - now())
      clearTimer(timer)
      timer = undefined
    },
  }
}
