import { api } from '@/services/api'
import type { LectureDetail } from '@/types/domain'

export const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp'
export const IMAGE_MAX_MB = 5

/** Quick client-side check for a friendlier message; the server validates the real bytes again. */
export function imageProblem(file: File): string | null {
  if (!IMAGE_ACCEPT.split(',').includes(file.type)) return 'Choose a JPG, PNG or WebP image.'
  if (file.size > IMAGE_MAX_MB * 1024 * 1024) return `Images must be smaller than ${IMAGE_MAX_MB} MB.`
  return null
}

export const uploadsApi = {
  /** Uploads one class photo through FastAPI; only its URL and metadata end up in the database. */
  addClassImage(lectureId: string, file: File, opts: { caption?: string; kind?: 'CLASS_EVIDENCE' | 'CHECKIN_IMAGE' } = {}) {
    const form = new FormData()
    form.append('file', file)
    if (opts.caption) form.append('caption', opts.caption)
    form.append('kind', opts.kind ?? 'CLASS_EVIDENCE')
    return api.post<LectureDetail>(`/lectures/${lectureId}/evidence`, form).then((r) => r.data)
  },
  removeClassImage: (materialId: string) => api.delete<LectureDetail>(`/lecture-evidence/${materialId}`).then((r) => r.data),
}

/** Image URLs are served by the API; relative ones go through the same origin / proxy as every other call. */
export function fileSrc(url: string): string {
  const base = (process.env.NEXT_PUBLIC_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''
  return url.startsWith('/') ? `${base}${url}` : url
}
