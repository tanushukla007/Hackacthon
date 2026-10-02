import { api } from './apiClient'
export const runTrace = (payload) => api.post('/trace', payload)
export const getTrace = (id) => api.get(`/trace/${id}`)
export const getTimeline = (id, buckets = 180) => api.get(`/trace/${id}/timeline?buckets=${buckets}`)
export const getTraceEvidence = (id) => api.get(`/trace/${id}/evidence`)
