// src/services/api.js — Axios API service
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 menit untuk LLM response
})

// Tambahkan token JWT ke setiap request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 — redirect ke login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.reload()
    }
    return Promise.reject(error)
  }
)

// ── Auth ──────────────────────────────────────────────
export const login = async (username, password) => {
  const form = new URLSearchParams()
  form.append('username', username)
  form.append('password', password)
  const res = await api.post('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data
}

export const register = async (username, email, password) => {
  const res = await api.post('/auth/register', { username, email, password })
  return res.data
}

// ── Chat ──────────────────────────────────────────────

// Streaming: /chat sekarang membalas NDJSON (satu baris JSON per event),
// bukan satu blob di akhir — dipakai `fetch` + ReadableStream secara
// langsung karena axios tidak punya cara sederhana & lintas-browser untuk
// membaca body secara bertahap. `callbacks` menerima:
//   onMeta(event)   -> sekali, sebelum token pertama {tool_used, sources}
//   onToken(text)   -> setiap potongan token jawaban
//   onDone()        -> sekali, setelah stream selesai normal
// Melempar Error kalau request gagal total (network/HTTP non-2xx).
export const sendMessageStream = async (sessionId, message, imageFilename, documentFilename, callbacks = {}, signal) => {
  const { onMeta, onToken, onDone } = callbacks
  const token = localStorage.getItem('access_token')

  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      image_filename: imageFilename,
      document_filename: documentFilename,
    }),
    signal,
  })

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem('access_token')
      window.location.reload()
    }
    let detail = 'Gagal menghubungi server.'
    try {
      const errBody = await response.json()
      detail = errBody.detail || detail
    } catch {
      // respons bukan JSON (mis. error jaringan mentah) — pakai pesan default
    }
    throw new Error(detail)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() ?? '' // baris terakhir bisa belum lengkap — simpan untuk potongan berikutnya

    for (const line of lines) {
      if (!line.trim()) continue
      const event = JSON.parse(line)
      if (event.type === 'meta') onMeta?.(event)
      else if (event.type === 'token') onToken?.(event.text)
      else if (event.type === 'error') throw new Error(event.detail || 'Terjadi kesalahan di server.')
      // "done" tidak perlu ditangani di sini — loop berakhir wajar saat
      // reader.read() mengembalikan done:true setelah baris ini.
    }
  }

  onDone?.()
}

export const getChatHistory = async (sessionId) => {
  const res = await api.get(`/chat/history?session_id=${sessionId}&limit=50`)
  return res.data
}

export const getChatSessions = async () => {
  const res = await api.get('/chat/sessions')
  return res.data
}

export const deleteChatSession = async (sessionId) => {
  const res = await api.delete(`/chat/sessions/${encodeURIComponent(sessionId)}`)
  return res.data
}

// ── Upload ────────────────────────────────────────────
// Sengaja tidak ada callback progress persentase — diukur langsung: transfer
// byte selesai dalam <1ms di localhost, sementara pemrosesan server
// (embedding dsb, 1-10 detik) tidak terukur oleh event upload-progress
// browser sama sekali. Angka % di titik itu cuma menampilkan "100%" lalu
// diam selama proses sebenarnya berjalan — terlihat macet padahal jujur
// tidak ada cara mengukurnya presisi dari sisi client (lihat UploadButton.jsx).
// Mengembalikan { job_id, filename, status: "processing", message } dengan
// CEPAT — server hanya memvalidasi dan menyimpan berkasnya. Ekstraksi teks,
// OCR, dan embedding berjalan di latar belakang; pantau dengan
// getUploadJob(job_id) sampai statusnya bukan "processing" lagi.
export const uploadFile = async (file) => {
  const form = new FormData()
  form.append('file', file)
  const res = await api.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export const getUploadJob = async (jobId) => {
  const res = await api.get(`/upload/jobs/${encodeURIComponent(jobId)}`)
  return res.data
}

// Jeda antar pengecekan status. Cukup rapat supaya berkas kecil (.txt selesai
// ~2 detik) tidak terasa tertahan, tapi tidak membanjiri server selama OCR
// yang bisa berjalan beberapa menit.
const POLL_INTERVAL_MS = 1000

// Pantau satu pekerjaan sampai selesai. Sengaja tanpa batas percobaan: OCR
// PDF 10 halaman bisa menyentuh ~5,5 menit, dan menyerah di tengah jalan
// justru membuat pengguna mengira unggahannya gagal padahal server masih
// mengerjakannya. `signal` dipakai untuk berhenti saat komponen dilepas.
export const waitForUploadJob = async (jobId, { signal } = {}) => {
  for (;;) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
    if (signal?.aborted) return null
    const job = await getUploadJob(jobId)
    if (job.status !== 'processing') return job
  }
}

// ── Documents (Knowledge Base) ─────────────────────────
export const getDocuments = async () => {
  const res = await api.get('/documents')
  return res.data
}

export const deleteDocument = async (filename) => {
  const res = await api.delete(`/documents/${encodeURIComponent(filename)}`)
  return res.data
}

// ── Health ────────────────────────────────────────────
export const checkHealth = async () => {
  const res = await api.get('/health')
  return res.data
}
