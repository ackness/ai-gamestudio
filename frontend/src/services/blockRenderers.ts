import { createElement } from 'react'
import type { ComponentType } from 'react'
import { useBlockSchemaStore } from '../stores/blockSchemaStore'
import { GenericBlockRenderer } from '../components/game/GenericBlockRenderer'

export interface BlockRendererProps {
  data: any
  blockId: string
  onAction: (msg: string) => void
  locked?: boolean
}

type BlockRenderer = ComponentType<BlockRendererProps>

const renderers = new Map<string, BlockRenderer>()

export function registerBlockRenderer(type: string, renderer: BlockRenderer): void {
  renderers.set(type, renderer)
}

/**
 * Look up a renderer for a block type.
 *
 * Priority:
 *  1. Explicitly registered custom renderer (e.g. choices, character_sheet)
 *  2. Schema-driven generic renderer (from plugin block declarations)
 *  3. undefined → caller falls back to FallbackBlock (collapsible JSON)
 */
export function getBlockRenderer(type: string): BlockRenderer | undefined {
  // 1. Custom registered renderer (highest priority)
  const custom = renderers.get(type)
  if (custom) return custom

  // 2. Schema-driven generic renderer
  const schema = useBlockSchemaStore.getState().schemas[type]
  if (schema) {
    // If schema references a named custom renderer, look it up
    if (schema.component === 'custom' && schema.renderer_name) {
      return renderers.get(schema.renderer_name)
    }
    // 'none' means backend-only, no UI
    if (schema.component === 'none') {
      return () => null
    }
    // Return a component that wraps GenericBlockRenderer with the resolved schema
    const SchemaRenderer: BlockRenderer = (props) =>
      createElement(GenericBlockRenderer, {
        data: props.data,
        blockId: props.blockId,
        schema,
        onAction: props.onAction,
      })
    SchemaRenderer.displayName = `SchemaRenderer(${type})`
    return SchemaRenderer
  }

  // 3. No renderer found
  return undefined
}
