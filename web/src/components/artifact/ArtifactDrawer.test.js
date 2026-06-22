import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import ArtifactDrawer from './ArtifactDrawer.vue'

/**
 * ArtifactDrawer 抽屉测试。
 *
 * 抽屉用 <Teleport to="body">，按钮渲染在 document.body，故直接查 body。
 * 按钮实际落在子组件 DocumentEditsArtifact / SolutionArtifact：
 *   - document_edits：写回 / 接受 / 拒绝 仅 isLatest 启用；定位始终启用
 *   - solution：     覆盖 仅 isLatest 启用；导出始终启用
 * isLatest=false → 禁用；isLatest=true → 启用且 emit 正确事件。
 */
function findBodyButton(text) {
  return Array.from(document.body.querySelectorAll('button')).find((b) =>
    (b.textContent || '').includes(text),
  )
}

const docArtifact = {
  artifact_type: 'document_edits',
  title: '编辑',
  summary: '2 处',
  payload: {
    replacements: [{ pattern: '旧', content: '新', reason: '润色' }],
    final_text: '新',
  },
}

const solutionArtifact = {
  artifact_type: 'solution',
  title: '方案',
  summary: 'v1',
  payload: { title: '方案', markdown: '# x', summary: 'v1' },
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('ArtifactDrawer - document_edits', () => {
  it('isLatest=false：写回/接受/拒绝按钮禁用，定位仍可用', () => {
    const wrapper = mount(ArtifactDrawer, {
      props: { open: true, artifact: docArtifact, isLatest: false },
    })
    const writeback = findBodyButton('写回')
    const accept = findBodyButton('接受')
    const reject = findBodyButton('拒绝')
    const locate = findBodyButton('定位')

    expect(writeback).toBeTruthy()
    expect(writeback.disabled).toBe(true)
    expect(accept.disabled).toBe(true)
    expect(reject.disabled).toBe(true)
    // 定位按钮不受 isLatest 影响，始终可用
    expect(locate.disabled).toBe(false)
    wrapper.unmount()
  })

  it('isLatest=true：接受/拒绝/写回启用且 emit 正确事件', async () => {
    const wrapper = mount(ArtifactDrawer, {
      props: { open: true, artifact: docArtifact, isLatest: true },
    })
    const accept = findBodyButton('接受')
    const reject = findBodyButton('拒绝')
    const writeback = findBodyButton('写回')

    expect(accept.disabled).toBe(false)
    expect(reject.disabled).toBe(false)
    expect(writeback.disabled).toBe(false)

    accept.click()
    await nextTick()
    expect(wrapper.emitted('accept')).toBeTruthy()
    expect(wrapper.emitted('accept')[0]).toEqual([{ pattern: '旧', index: 0 }])

    reject.click()
    await nextTick()
    expect(wrapper.emitted('reject')).toBeTruthy()
    expect(wrapper.emitted('reject')[0]).toEqual([{ pattern: '旧', index: 0 }])

    writeback.click()
    await nextTick()
    expect(wrapper.emitted('writeback')).toBeTruthy()
    wrapper.unmount()
  })
})

describe('ArtifactDrawer - solution', () => {
  it('isLatest=false：覆盖按钮禁用，导出仍可用', () => {
    const wrapper = mount(ArtifactDrawer, {
      props: { open: true, artifact: solutionArtifact, isLatest: false },
    })
    const overwrite = findBodyButton('覆盖')
    const exportBtn = findBodyButton('导出')
    expect(overwrite.disabled).toBe(true)
    expect(exportBtn.disabled).toBe(false)
    wrapper.unmount()
  })

  it('isLatest=true：覆盖/导出启用且 emit overwriteSolution / exportSolution', async () => {
    const wrapper = mount(ArtifactDrawer, {
      props: { open: true, artifact: solutionArtifact, isLatest: true },
    })
    const overwrite = findBodyButton('覆盖')
    const exportBtn = findBodyButton('导出')

    expect(overwrite.disabled).toBe(false)

    exportBtn.click()
    await nextTick()
    expect(wrapper.emitted('exportSolution')).toBeTruthy()

    overwrite.click()
    await nextTick()
    expect(wrapper.emitted('overwriteSolution')).toBeTruthy()
    wrapper.unmount()
  })
})
