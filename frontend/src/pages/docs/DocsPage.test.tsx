import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { DocsPage } from './DocsPage'

describe('DocsPage', () => {
  it('renders the public documentation sections without signing in', () => {
    render(<MemoryRouter><DocsPage /></MemoryRouter>)
    for (const title of ['System architecture', 'Hiring workflow', 'The three AI agents', 'Human-in-the-loop controls', 'Security & privacy']) {
      expect(screen.getByRole('heading', { level: 2, name: title })).toBeInTheDocument()
    }
    expect(screen.getByRole('heading', { name: 'Resume Scoring Agent' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
  })
})
