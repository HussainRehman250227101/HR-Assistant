import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { DateInput } from '../components/ui'
import { displayToIsoDate, formatDate, formatInZone, isoToDisplayDate, maskDateInput } from './format'

describe('DD/MM/YYYY helpers', () => {
  it('converts between ISO and DD/MM/YYYY', () => {
    expect(isoToDisplayDate('2026-11-08')).toBe('08/11/2026')
    expect(isoToDisplayDate('')).toBe('')
    expect(isoToDisplayDate('garbage')).toBe('')
    expect(displayToIsoDate('08/11/2026')).toBe('2026-11-08')
  })

  it('rejects text that is not a real calendar date', () => {
    for (const bad of ['31/02/2026', '32/01/2026', '00/10/2026', '08/13/2026', '8/11/2026', '08-11-2026', '08/11/26', '']) {
      expect(displayToIsoDate(bad)).toBe('')
    }
    expect(displayToIsoDate('29/02/2028')).toBe('2028-02-29')
    expect(displayToIsoDate('29/02/2027')).toBe('')
  })

  it('masks typing into DD/MM/YYYY', () => {
    expect(maskDateInput('0')).toBe('0')
    expect(maskDateInput('081')).toBe('08/1')
    expect(maskDateInput('0811')).toBe('08/11')
    expect(maskDateInput('08112026')).toBe('08/11/2026')
    expect(maskDateInput('08/11/20269999')).toBe('08/11/2026')
    expect(maskDateInput('ab08cd')).toBe('08')
  })

  it('formats dates and instants as DD/MM/YYYY', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('2026-12-31', false)).toBe('31/12/2026') // date-only values are never time-zone shifted
    expect(formatDate('2026-12-31')).toBe('31/12/2026')
    expect(formatDate('2026-11-08T14:30:00Z', false)).toMatch(/^\d{2}\/\d{2}\/\d{4}$/)
    expect(formatDate('2026-11-08T14:30:00Z')).toMatch(/^\d{2}\/\d{2}\/\d{4}, \d{2}:\d{2}$/)
    expect(formatInZone('2026-11-10T06:00:00Z', 'Asia/Karachi')).toBe('Tue 10/11/2026, 11:00 (Asia/Karachi)')
    expect(formatInZone('2026-11-10T06:00:00Z', 'Asia/Karachi', false)).toBe('Tue 10/11/2026, 11:00')
  })
})

function Harness({ initial = '', onValue }: { initial?: string; onValue?: (iso: string) => void }) {
  const [value, setValue] = useState(initial)
  return <DateInput required value={value} onChange={(iso) => { setValue(iso); onValue?.(iso) }} />
}

describe('DateInput', () => {
  it('shows an ISO value as DD/MM/YYYY', () => {
    render(<Harness initial="2026-11-08" />)
    expect(screen.getByPlaceholderText('DD/MM/YYYY')).toHaveValue('08/11/2026')
  })

  it('accepts typed DD/MM/YYYY and reports an ISO date', async () => {
    const seen: string[] = []
    render(<Harness onValue={(iso) => seen.push(iso)} />)
    const input = screen.getByPlaceholderText('DD/MM/YYYY')
    await userEvent.type(input, '08112026')
    expect(input).toHaveValue('08/11/2026')
    expect(seen.at(-1)).toBe('2026-11-08')
    expect(input).toBeValid()
  })

  it('reports nothing and flags the field while the date is incomplete or not real', async () => {
    const seen: string[] = []
    render(<Harness onValue={(iso) => seen.push(iso)} />)
    const input = screen.getByPlaceholderText('DD/MM/YYYY') as HTMLInputElement
    await userEvent.type(input, '3102')
    expect(input).toHaveValue('31/02')
    expect(seen.at(-1)).toBe('')
    await userEvent.type(input, '2026')
    expect(input).toHaveValue('31/02/2026')
    expect(seen.at(-1)).toBe('')
    expect(input.checkValidity()).toBe(false)
    expect(input.validationMessage).toMatch(/DD\/MM\/YYYY/)
  })
})
