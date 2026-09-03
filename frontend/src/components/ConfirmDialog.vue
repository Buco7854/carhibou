<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppModal from './AppModal.vue'
import { acceptConfirm, closeConfirm, confirmBusy, confirmError, confirmOption, confirmRequest } from '../confirm'

const { t } = useI18n()
</script>

<template>
  <AppModal :open="Boolean(confirmRequest)" :title="confirmRequest?.title ?? ''" @close="closeConfirm">
    <div v-if="confirmRequest" class="confirm-body">
      <p class="confirm-question">{{ confirmRequest.question }}</p>
      <p v-if="confirmRequest.detail" class="field-hint">{{ confirmRequest.detail }}</p>

      <!-- The destructive half of a choice is never the default: it is opted
           into here, next to what it costs. -->
      <label v-if="confirmRequest.option" class="confirm-option">
        <input v-model="confirmOption" type="checkbox" :disabled="confirmBusy" />
        <span>
          <strong>{{ confirmRequest.option.label }}</strong>
          <small v-if="confirmRequest.option.detail">{{ confirmRequest.option.detail }}</small>
        </span>
      </label>

      <p v-if="confirmError" class="error" role="alert">{{ confirmError }}</p>

      <div class="form-actions">
        <button class="button danger" type="button" :disabled="confirmBusy" @click="acceptConfirm">
          {{ confirmBusy ? (confirmRequest.busyLabel ?? t('common.working')) : confirmRequest.confirmLabel }}
        </button>
        <button class="button ghost" type="button" :disabled="confirmBusy" @click="closeConfirm">{{ t('common.cancel') }}</button>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.confirm-body{display:grid;gap:14px}
.confirm-question{margin:0;font-size:var(--font-body);font-weight:500}
/* The option reads as a decision with a price, not as a preference. */
.confirm-option{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:start;gap:9px;padding:11px 12px;border:1px solid var(--line);border-radius:var(--radius);cursor:pointer}
.confirm-option:has(input:checked){border-color:var(--danger);background:color-mix(in srgb,var(--danger) 7%,transparent)}
.confirm-option input{width:15px;height:15px;margin-top:1px;accent-color:var(--danger)}
.confirm-option span{display:grid;gap:2px}
.confirm-option strong{font-size:var(--font-body);font-weight:500}
.confirm-option small{color:var(--muted);font-size:var(--font-caption);line-height:1.45}
</style>
