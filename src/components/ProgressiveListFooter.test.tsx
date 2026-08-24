import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ProgressiveListFooter from './ProgressiveListFooter'


describe('ProgressiveListFooter', () => {
  afterEach(cleanup)

  it('reports mounted rows and exposes incremental and full rendering actions', async () => {
    const onMore = vi.fn()
    const onAll = vi.fn()
    render(<ProgressiveListFooter shown={50} total={1216} step={50} onMore={onMore} onAll={onAll} />)

    expect(screen.getByText('Показано 50 из 1 216')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Показать ещё 50' }))
    await userEvent.setup().click(screen.getByRole('button', { name: 'Показать все 1 216' }))
    expect(onMore).toHaveBeenCalledOnce()
    expect(onAll).toHaveBeenCalledOnce()
  })

  it('does not render when every row is already mounted', () => {
    const { container } = render(<ProgressiveListFooter shown={12} total={12} step={50} onMore={vi.fn()} onAll={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })
})
