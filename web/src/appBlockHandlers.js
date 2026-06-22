function genLocalBlockId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return 'local-' + crypto.randomUUID()
  }
  return 'local-' + Date.now() + '-' + Math.random().toString(36).slice(2)
}

export function onSplitBlock(blocks, blockId, cursorPos, textBefore, textAfter, textToBlockXml) {
  const idx = blocks.findIndex((b) => b.block_id === blockId)
  if (idx < 0) return blocks

  const orig = blocks[idx]
  const updatedOrig = {
    ...orig,
    text: textBefore,
    pending_xml: textToBlockXml(orig.kind, textBefore),
    edited: true,
  }
  const newBlock = {
    block_id: genLocalBlockId(),
    kind: orig.kind,
    text: textAfter,
    raw_xml: '',
    level: orig.level ?? 0,
    original_text: textAfter,
    original_xml: '',
    edited: true,
    suggestion: null,
    pending_xml: textToBlockXml(orig.kind, textAfter),
  }

  return [...blocks.slice(0, idx), updatedOrig, newBlock, ...blocks.slice(idx + 1)]
}

export function onMergeBlocks(blocks, currentId, prevId, textToBlockXml) {
  const curIdx = blocks.findIndex((b) => b.block_id === currentId)
  const prevIdx = blocks.findIndex((b) => b.block_id === prevId)
  if (curIdx < 0 || prevIdx < 0) return blocks

  const cur = blocks[curIdx]
  return blocks
    .map((block, idx) => {
      if (idx !== prevIdx) return block
      const text = block.text + (cur.text || '')
      return {
        ...block,
        text,
        pending_xml: textToBlockXml(block.kind, text),
        edited: true,
      }
    })
    .filter((_, idx) => idx !== curIdx)
}

export function onChangeBlockKind(blocks, blockId, newKind, cleanedText, textToBlockXml) {
  const idx = blocks.findIndex((b) => b.block_id === blockId)
  if (idx < 0) return blocks

  return blocks.map((block, i) =>
    i === idx
      ? {
          ...block,
          kind: newKind,
          text: cleanedText,
          pending_xml: textToBlockXml(newKind, cleanedText),
          edited: true,
        }
      : block,
  )
}

export function onBlocksChanged(blocks, updates, textToBlockXml) {
  if (!Array.isArray(updates)) return blocks

  const byId = new Map()
  for (const update of updates) {
    const id = update.block_id ?? update.blockId
    if (id !== undefined && id !== null) byId.set(id, update.text ?? '')
  }
  if (byId.size === 0) return blocks

  return blocks.map((block) => {
    if (!byId.has(block.block_id)) return block
    const text = byId.get(block.block_id)
    return {
      ...block,
      text,
      pending_xml: textToBlockXml(block.kind, text),
      edited: true,
    }
  })
}
