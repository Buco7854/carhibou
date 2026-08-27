<script setup lang="ts">
import { python } from '@codemirror/lang-python'
import { Compartment } from '@codemirror/state'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView } from '@codemirror/view'
import { basicSetup } from 'codemirror'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { resolvedTheme } from '../theme'

const model = defineModel<string>({ required:true })
const host = ref<HTMLDivElement>()
let view:EditorView|undefined
const theme = new Compartment()
onMounted(()=>{
  view=new EditorView({
    doc:model.value,
    extensions:[basicSetup,python(),theme.of(resolvedTheme.value==='dark'?oneDark:[]),EditorView.lineWrapping,EditorView.updateListener.of(update=>{if(update.docChanged)model.value=update.state.doc.toString()})],
    parent:host.value!,
  })
})
watch(model,(value)=>{if(view&&value!==view.state.doc.toString())view.dispatch({changes:{from:0,to:view.state.doc.length,insert:value}})})
watch(resolvedTheme,(value)=>view?.dispatch({effects:theme.reconfigure(value==='dark'?oneDark:[])}))
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
