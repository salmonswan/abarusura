import { describe, expect, it } from 'vitest'
import { directusUrl } from './config'

describe('directusUrl', () => {
  it('defaults to the local Directus', () => {
    expect(directusUrl({})).toBe('http://localhost:8065')
  })
  it('uses the configured address without a trailing slash', () => {
    expect(directusUrl({ VITE_DIRECTUS_URL: 'https://cms.example.org/'
})).toBe('https://cms.example.org')
  })
})
