/**
 * Cliente HTTP do painel. A sessão viaja no cookie HttpOnly (o navegador cuida);
 * como a API está na mesma origem, o `Sec-Fetch-Site: same-origin` exigido pelo backend vai sozinho.
 */

export class ApiError extends Error {
  status: number
  detail: string
  data: unknown

  constructor(status: number, detail: string, data: unknown) {
    super(detail)
    this.status = status
    this.detail = detail
    this.data = data
  }
}

export const UNAUTHORIZED_EVENT = 'kadosh:unauthorized'
export const MUST_CHANGE_PASSWORD_EVENT = 'kadosh:must-change-password'

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

interface Options {
  method?: Method
  body?: unknown
  query?: Record<string, string | number | boolean | Array<string | number> | undefined | null>
  signal?: AbortSignal
}

function buildQuery(query?: Options['query']): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue
    // lista vira repetição do parâmetro: ?status=agendado&status=confirmado
    if (Array.isArray(v)) v.forEach((item) => params.append(k, String(item)))
    else params.set(k, String(v))
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

/** Extrai uma mensagem legível de qualquer erro da API (inclusive 422 do Pydantic). */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  if (err instanceof TypeError) return 'Sem conexão com o servidor. Verifique a rede e tente de novo.'
  if (err instanceof Error) return err.message
  return 'Erro inesperado.'
}

export function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404
}

function detailFrom(status: number, data: unknown): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = (data as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      // 422 do Pydantic: [{loc: ['body','campo'], msg: '...'}]
      return d
        .map((e) => {
          const loc = Array.isArray(e.loc) ? e.loc.filter((p: unknown) => p !== 'body').join('.') : ''
          const msg = String(e.msg ?? '').replace(/^Value error, /, '')
          return loc ? `${loc}: ${msg}` : msg
        })
        .join(' · ')
    }
  }
  if (status === 401) return 'Sessão expirada. Entre novamente.'
  if (status === 403) return 'Sem permissão para esta ação.'
  if (status === 404) return 'Registro não encontrado.'
  if (status >= 500) return 'Erro no servidor. Tente novamente.'
  return `Erro ${status}.`
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const { method = 'GET', body, query, signal } = opts
  const res = await fetch(`/api/v1${path}${buildQuery(query)}`, {
    method,
    credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  })

  if (res.status === 204) return undefined as T

  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }

  if (!res.ok) {
    const detail = detailFrom(res.status, data)
    // /auth/* trata o próprio 401 (o `me` devolve null e o guard redireciona com `from`)
    if (res.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
    }
    if (res.status === 403 && detail.startsWith('Troque sua senha')) {
      window.dispatchEvent(new CustomEvent(MUST_CHANGE_PASSWORD_EVENT))
    }
    throw new ApiError(res.status, detail, data)
  }
  return data as T
}
