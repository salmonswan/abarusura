import { describe, expect, it } from 'vitest'
import { photos } from './photos'

describe('photos', () => {
  it('lists the three opening photos in order with descriptive alt text', () => {
    expect(photos).toEqual([
      { file: 'hero-wide.jpg', alt: "Abarusura women's side running in attack" },
      { file: 'clip10.jpg', alt: 'Players smiling before a match' },
      { file: 'hero.jpg', alt: 'A ball carrier breaks through' },
    ])
  })

  it('uses JPEG filenames without paths and nonempty alt text', () => {
    for (const { file, alt } of photos) {
      expect(file).toMatch(/^[^/]+\.jpg$/)
      expect(alt.trim()).not.toBe('')
    }
  })
})
