import { afterEach, describe, expect, it, vi } from 'vitest'
import { exportDoc } from './api.js'

function makeResponse(blob, headers = {}) {
  return {
    ok: true,
    status: 200,
    headers: { get: (name) => headers[name.toLowerCase()] || null },
    blob: vi.fn(async () => blob),
  }
}

describe('api exportDoc', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('用 url 和 format 调用后端并触发浏览器下载', async () => {
    const blob = new Blob(['docx'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(makeResponse(blob, { 'content-disposition': 'attachment; filename="weekly.docx"' }))
    const objectUrlMock = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeMock = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const clickMock = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    await exportDoc('https://example.feishu.cn/docx/fake', 'docx', 'weekly')

    expect(fetchMock).toHaveBeenCalledWith('/api/doc/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: 'https://example.feishu.cn/docx/fake',
        format: 'docx',
        filename: 'weekly',
      }),
    })
    expect(objectUrlMock).toHaveBeenCalledWith(blob)
    expect(clickMock).toHaveBeenCalled()
    expect(revokeMock).toHaveBeenCalledWith('blob:test')
  })
})
