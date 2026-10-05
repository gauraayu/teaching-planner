/** User Management API (admin only). Pages never build these URLs themselves. */
import { api, type Paged } from '@/services/api'
import type { ManagedUser, Role, ScopeMode } from '@/types/domain'

export type ScopeInput = { mode: ScopeMode; department_id: string | null; semester_numbers: number[]; section_names: string[]; subject_ids: string[] }

export type UserInput = {
  full_name: string
  employee_id: string
  email: string
  username: string | null
  role: Role
  department_id: string | null
  designation: string | null
  phone: string | null
  is_active: boolean
  scope: ScopeInput
}

export const usersApi = {
  list: (params: { role?: Role | ''; status?: 'ACTIVE' | 'INACTIVE' | ''; q?: string; subject_id?: string }) =>
    api.get<Paged<ManagedUser>>('/admin/users', { params: Object.fromEntries(Object.entries(params).filter(([, v]) => v)) }).then((r) => r.data),
  get: (id: string) => api.get<ManagedUser>(`/admin/users/${id}`).then((r) => r.data),
  create: (body: UserInput & { password: string }) => api.post<ManagedUser>('/admin/users', body).then((r) => r.data),
  update: (id: string, body: Partial<UserInput>) => api.patch<ManagedUser>(`/admin/users/${id}`, body).then((r) => r.data),
  setActive: (id: string, is_active: boolean) => api.patch<ManagedUser>(`/admin/users/${id}`, { is_active }).then((r) => r.data),
  resetPassword: (id: string, password: string) => api.post<ManagedUser>(`/admin/users/${id}/password`, { password }).then((r) => r.data),
}

/** Path + params for the professor dropdowns: real, active professor accounts, optionally only those eligible for a subject. */
export const PROFESSOR_OPTIONS = '/admin/users'
export const professorParams = (subjectId?: string | null) => ({ role: 'PROFESSOR', status: 'ACTIVE', subject_id: subjectId ?? undefined })
export const professorLabel = (u: { full_name: string; employee_id?: string | null }) => (u.employee_id ? `${u.full_name} · ${u.employee_id}` : u.full_name)
