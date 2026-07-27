import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Play, Plus, Settings2 } from 'lucide-react'

import PageGuide from './PageGuide'
import type { GuideStep } from './PageGuide'

const STEPS: GuideStep[] = [
  {
    title: 'Добавьте проект',
    body: 'Укажите путь к папке на диске.',
    icon: Plus,
    control: 'Добавить проект',
    selector: '[data-test="add"]',
  },
  {
    title: 'Шаг без якоря',
    body: 'Этот шаг только читается, подсвечивать нечего.',
    icon: Settings2,
    hint: 'Порт 5173 занят самим SemixCRM.',
  },
  {
    title: 'Запустите проект',
    body: 'Команда стартует в папке проекта.',
    icon: Play,
    selector: '[data-test="run"]',
  },
  {
    title: 'Элемента нет на странице',
    body: 'Тур должен пропустить этот шаг.',
    icon: Play,
    selector: '[data-test="missing"]',
  },
]

function renderGuide() {
  return render(
    <div>
      <button type="button" data-test="add">Добавить проект</button>
      <button type="button" data-test="run">Запустить</button>
      <PageGuide sectionId="test" title="Как пользоваться разделом" intro="Короткая вводная." steps={STEPS} />
    </div>,
  )
}

describe('инструкция на странице', () => {
  beforeEach(() => {
    window.localStorage.clear()
    // jsdom не реализует scrollIntoView, а тур его вызывает.
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('при первом заходе раскрывается сама и показывает все шаги', () => {
    renderGuide()

    expect(screen.getByRole('heading', { name: 'Как пользоваться разделом' })).toBeInTheDocument()
    expect(screen.getByText('Добавьте проект')).toBeInTheDocument()
    expect(screen.getByText('Запустите проект')).toBeInTheDocument()
    expect(screen.getByText('Добавить проект', { selector: '.guide-control-chip' })).toBeInTheDocument()
    expect(screen.getByText(/Порт 5173 занят/)).toBeInTheDocument()
  })

  it('при повторном заходе остаётся свёрнутой', () => {
    renderGuide()
    cleanup()
    renderGuide()

    expect(screen.queryByText('Добавьте проект')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Как пользоваться' })).toBeInTheDocument()
  })

  it('сворачивается и разворачивается кнопкой', async () => {
    const user = userEvent.setup()
    renderGuide()

    await user.click(screen.getByRole('button', { name: 'Свернуть' }))
    expect(screen.queryByText('Добавьте проект')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Как пользоваться' }))
    expect(screen.getByText('Добавьте проект')).toBeInTheDocument()
  })

  it('тур подсвечивает элемент, который описывает текущий шаг', async () => {
    const user = userEvent.setup()
    renderGuide()

    await user.click(screen.getByRole('button', { name: 'Показать на экране' }))

    const tip = await screen.findByRole('dialog')
    expect(tip).toHaveAttribute('data-active-selector', '[data-test="add"]')
    expect(within(tip).getByText('1 из 3')).toBeInTheDocument()
  })

  it('в тур попадают только шаги с якорем', async () => {
    const user = userEvent.setup()
    renderGuide()

    await user.click(screen.getByRole('button', { name: 'Показать на экране' }))
    const tip = await screen.findByRole('dialog')

    // Шагов четыре, но у одного нет селектора, а у другого нет элемента на странице.
    expect(within(tip).getByText('1 из 3')).toBeInTheDocument()
  })

  it('«Далее» переводит на следующий существующий элемент', async () => {
    const user = userEvent.setup()
    renderGuide()

    await user.click(screen.getByRole('button', { name: 'Показать на экране' }))
    await user.click(await screen.findByRole('button', { name: /Далее/ }))

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toHaveAttribute('data-active-selector', '[data-test="run"]')
    })
  })

  it('на последнем доступном шаге предлагает «Готово»', async () => {
    const user = userEvent.setup()
    renderGuide()

    await user.click(screen.getByRole('button', { name: 'Показать на экране' }))
    await user.click(await screen.findByRole('button', { name: /Далее/ }))

    // Четвёртый шаг ссылается на отсутствующий элемент, поэтому дальше идти некуда.
    expect(await screen.findByRole('button', { name: 'Готово' })).toBeInTheDocument()
  })

  it('закрывается по Escape', async () => {
    const user = userEvent.setup()
    renderGuide()

    await user.click(screen.getByRole('button', { name: 'Показать на экране' }))
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('не показывает кнопку тура, когда инструкция свёрнута', async () => {
    const user = userEvent.setup()
    renderGuide()

    await user.click(screen.getByRole('button', { name: 'Свернуть' }))

    expect(screen.queryByRole('button', { name: 'Показать на экране' })).not.toBeInTheDocument()
  })
})
