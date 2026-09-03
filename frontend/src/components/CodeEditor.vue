<script setup lang="ts">
import { python } from '@codemirror/lang-python'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { Compartment, Prec, type Extension } from '@codemirror/state'
import { oneDark } from '@codemirror/theme-one-dark'
import { tags } from '@lezer/highlight'
import { EditorView } from '@codemirror/view'
import { basicSetup } from 'codemirror'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { resolvedTheme } from '../theme'

const props = defineProps<{ label: string }>()
const model = defineModel<string>({ required:true })
const host = ref<HTMLDivElement>()
let view:EditorView|undefined
const theme = new Compartment()

/* One Dark paints these tags in a coral that measures 4.08:1 on its own
   active-line background and 4.38:1 on the plain one, both under the 4.5:1 the
   rest of the interface is held to. Lightened only as far as clearing it. */
const readableCoral = syntaxHighlighting(HighlightStyle.define([
  { tag:[tags.name,tags.deleted,tags.character,tags.propertyName,tags.macroName], color:'#e77a83' },
  { tag:tags.heading, fontWeight:'bold', color:'#e77a83' },
  // Its violet keywords measure 4.43:1 on the active line, under the same
  // 4.5:1 the coral above was lightened for.
  { tag:tags.keyword, color:'#ca7ce1' },
]))
const darkTheme = ():Extension[] => [oneDark, Prec.high(readableCoral)]
onMounted(()=>{
  view=new EditorView({
    doc:model.value,
    extensions:[basicSetup,python(),theme.of(resolvedTheme.value==='dark'?darkTheme():[]),EditorView.lineWrapping,EditorView.contentAttributes.of({ 'aria-label':props.label }),EditorView.updateListener.of(update=>{if(update.docChanged)model.value=update.state.doc.toString()})],
    parent:host.value!,
  })
})
watch(model,(value)=>{if(view&&value!==view.state.doc.toString())view.dispatch({changes:{from:0,to:view.state.doc.length,insert:value}})})
watch(resolvedTheme,(value)=>view?.dispatch({effects:theme.reconfigure(value==='dark'?darkTheme():[])}))
onBeforeUnmount(()=>view?.destroy())
</script>
<template><div ref="host" class="code-editor" /></template>
<style scoped>
.code-editor{overflow:hidden;background:var(--input);border:1px solid var(--line-strong);border-radius:var(--radius)}
:deep(.cm-editor){height:260px;font-size:13px}
:deep(.cm-scroller){font-family:var(--mono)}
:deep(.cm-editor.cm-focused){outline:0}
.code-editor:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
:deep(.cm-gutters){background:var(--panel-2);border-right:1px solid var(--line)}
@media(max-width:620px){:deep(.cm-editor){height:220px}}
</style>
