import { api } from './apiClient'
export const getAccount = (id) => api.get(`/accounts/${id}`)
export const getAccountTransactions = (id, { direction = 'all', limit = 100, offset = 0 } = {}) =>
  api.get(`/accounts/${id}/transactions?direction=${direction}&limit=${limit}&offset=${offset}`)
export const getCounterparties = (id, limit = 25) => api.get(`/accounts/${id}/counterparties?limit=${limit}`)
export const searchAccounts = (q) => api.get(`/accounts/search?q=${encodeURIComponent(q)}`)
export const getTransaction = (tid) => api.get(`/transactions/${encodeURIComponent(tid)}`)
export const getSourceRow = (rowId) => api.get(`/rows/${rowId}`)
