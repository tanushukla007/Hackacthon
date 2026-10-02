import { api } from './apiClient'
export const getSystemStatus = () => api.get('/system/status')
export const getIngestStatus = () => api.get('/ingest/status')
export const startIngest = (filename) => api.post('/ingest', { filename })
export const getProfile = () => api.get('/ingest/profile')
export const getDatasetSummary = () => api.get('/dataset/summary')
export const getRiskDistribution = () => api.get('/accounts/risk-distribution')
export const getTopAccounts = (limit = 25) => api.get(`/accounts/top?limit=${limit}`)
