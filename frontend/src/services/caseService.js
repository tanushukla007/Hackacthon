import { api } from './apiClient'
export const listCases = () => api.get('/cases')
export const createCase = (payload) => api.post('/cases', payload)
export const getCase = (id) => api.get(`/cases/${id}`)
export const addEvidence = (id, items) => api.post(`/cases/${id}/evidence`, { items })
export const addDiary = (id, entry) => api.post(`/cases/${id}/diary`, entry)
export const generateFreezeRequisition = (id, accounts) =>
  api.post(`/cases/${id}/documents/freeze-requisition`, { accounts })
