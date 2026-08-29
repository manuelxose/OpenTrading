import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { App, TradeDrawer } from './App'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({ schemaVersion: '1.0.0', data: {
      asOf: '2026-08-28T10:00:00Z', operatingMode: 'PAPER',
      account: { nav: '100000', equity: '100000', currency: 'USD' },
      performance: { pnl: '0', drawdownPct: 0 }, exposure: { gross: '0', net: '0' },
      riskStatus: 'NORMAL', mt4Status: 'CONNECTED',
      dataFreshness: { status: 'FRESH', latestAt: '2026-08-28T10:00:00Z' },
    } }),
  })))
})

afterEach(() => cleanup())

test('renders the complete navigation and live overview', async () => {
  render(<App />)
  await waitFor(() => expect(screen.getAllByText('$100,000')).toHaveLength(2))
  expect(screen.getByText(/Live/)).toBeInTheDocument()
  for (const label of ['Overview', 'Research', 'Signals', 'Risk', 'Orders', 'Trades', 'Positions', 'Backtests', 'Memory', 'Agents', 'System']) {
    expect(screen.getAllByText(label).length).toBeGreaterThan(0)
  }
  expect(screen.getByText('PAPER')).toBeInTheDocument()
})

function DrawerHarness() {
  const [open, setOpen] = useState(false)
  return <><div className="workspace"><button onClick={() => setOpen(true)}>Open trade</button></div>{open && <TradeDrawer id="trade-1" close={() => setOpen(false)} />}</>
}

test('trade dialog traps focus, closes on Escape, and restores focus', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({ schemaVersion: '1.0.0', data: { tradeId: 'trade-1', traceId: 'trace-1', stages: [] } }),
  })))
  render(<DrawerHarness />)
  const trigger = screen.getByRole('button', { name: 'Open trade' })
  trigger.focus()
  fireEvent.click(trigger)
  const dialog = await screen.findByRole('dialog')
  const close = dialog.querySelector('button')!
  await waitFor(() => expect(close).toHaveFocus())
  fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
  expect(close).toHaveFocus()
  expect(document.querySelector('.workspace')).toHaveProperty('inert', true)
  fireEvent.keyDown(document, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(trigger).toHaveFocus()
  expect(document.querySelector('.workspace')).toHaveProperty('inert', false)
})
