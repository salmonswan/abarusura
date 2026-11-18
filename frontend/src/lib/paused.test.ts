import { describe, expect, it, vi } from 'vitest'
import { readPaused, writePaused } from './paused'

describe('pause storage', () => {
  it.each(['0', null, '', 'true'])('reads %s as playing', (value) => {
    expect(readPaused({ getItem: () => value })).toBe(false)
  })

  it('reads only the saved flag as paused', () => {
    const getItem = vi.fn(() => '1')
    expect(readPaused({ getItem })).toBe(true)
    expect(getItem).toHaveBeenCalledWith('abar-paused')
  })

  it('plays when storage cannot be read', () => {
    expect(readPaused({ getItem: () => { throw new Error('blocked') } })).toBe(false)
  })

  it('writes both pause states', () => {
    const setItem = vi.fn()
    writePaused({ setItem }, true)
    writePaused({ setItem }, false)
    expect(setItem.mock.calls).toEqual([['abar-paused', '1'], ['abar-paused', '0']])
  })

  it('ignores blocked storage writes', () => {
    expect(() => writePaused({ setItem: () => { throw new Error('blocked') } }, true)).not.toThrow()
  })
})
