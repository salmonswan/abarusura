import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSlideshow } from './slideshow'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

function setup() {
  const onShow = vi.fn()
  const slideshow = createSlideshow({
    count: 3,
    ms: 6000,
    onShow,
    now: () => Date.now(),
    setTimer: (callback, delay) => setTimeout(callback, delay),
    clearTimer: (timer) => clearTimeout(timer),
  })
  return { slideshow, onShow }
}

describe('slideshow', () => {
  it('starts on the first photo without scheduling until play', () => {
    const { slideshow, onShow } = setup()
    expect(slideshow.index).toBe(0)
    vi.advanceTimersByTime(20000)
    expect(onShow).not.toHaveBeenCalled()
  })

  it('shows the second photo after six seconds and wraps after the third', () => {
    const { slideshow, onShow } = setup()
    slideshow.play()
    vi.advanceTimersByTime(5999)
    expect(slideshow.index).toBe(0)
    vi.advanceTimersByTime(1)
    expect(slideshow.index).toBe(1)
    vi.advanceTimersByTime(6000)
    expect(slideshow.index).toBe(2)
    vi.advanceTimersByTime(6000)
    expect(slideshow.index).toBe(0)
    expect(onShow.mock.calls).toEqual([[1], [2], [0]])
    slideshow.pause()
  })

  it('keeps the remaining time while paused', () => {
    const { slideshow, onShow } = setup()
    slideshow.play()
    vi.advanceTimersByTime(2000)
    slideshow.pause()
    vi.advanceTimersByTime(20000)
    expect(slideshow.index).toBe(0)
    expect(onShow).not.toHaveBeenCalled()
    slideshow.play()
    vi.advanceTimersByTime(3999)
    expect(slideshow.index).toBe(0)
    vi.advanceTimersByTime(1)
    expect(slideshow.index).toBe(1)
    slideshow.pause()
  })

  it('does not duplicate timers or lose time on repeated play and pause', () => {
    const { slideshow, onShow } = setup()
    slideshow.pause()
    slideshow.play()
    vi.advanceTimersByTime(2000)
    slideshow.play()
    slideshow.pause()
    vi.advanceTimersByTime(1000)
    slideshow.pause()
    slideshow.play()
    vi.advanceTimersByTime(4000)
    expect(onShow.mock.calls).toEqual([[1]])
    slideshow.pause()
    vi.advanceTimersByTime(20000)
    expect(onShow).toHaveBeenCalledTimes(1)
  })
})
