import type { Benchmark, BenchmarkProfile, ChunkingPreview, Evaluation, Health, PipelineStage, StreamMessage } from '../types/api'

async function checked(response: Response) {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try { detail = (await response.json()).detail ?? detail } catch { /* safe fallback */ }
    throw new Error(detail)
  }
  return response
}

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  return (await checked(await fetch('/api/health', { signal }))).json()
}

export async function getBenchmark(signal?: AbortSignal): Promise<Benchmark> {
  return (await checked(await fetch('/api/benchmark', { signal }))).json()
}

export async function getBenchmarkProfiles(signal?: AbortSignal): Promise<BenchmarkProfile[]> {
  const response = await checked(await fetch('/api/benchmark/profiles', { signal }))
  return response.json().then((value: { profiles: BenchmarkProfile[] }) => value.profiles)
}

export async function getMetrics(signal?: AbortSignal): Promise<{ stage_means_ms: Record<string, number>; sample_count: number }> {
  return (await checked(await fetch('/api/metrics', { signal }))).json()
}

export async function getPipeline(signal?: AbortSignal): Promise<PipelineStage[]> {
  return (await checked(await fetch('/api/pipeline', { signal }))).json().then((value: { stages: PipelineStage[] }) => value.stages)
}

export async function getEvaluation(signal?: AbortSignal): Promise<Evaluation> {
  return (await checked(await fetch('/api/evaluation', { signal }))).json()
}

export async function getChunkingPreview(signal?: AbortSignal): Promise<ChunkingPreview> {
  return (await checked(await fetch('/api/chunking/preview', { signal }))).json()
}

async function readNDJSON(response: Response, onMessage: (message: StreamMessage) => void, signal?: AbortSignal) {
  await checked(response)
  if (!response.body) throw new Error('Streaming response is not supported by this browser')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminal = false // saw a result/error message
  const wrapped = (message: StreamMessage) => {
    if (message.type === 'result' || message.type === 'error') terminal = true
    onMessage(message)
  }

  const readLoop = (async () => {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) if (line.trim()) wrapped(JSON.parse(line) as StreamMessage)
    }
  })()

  // Hard cap: never let a hung/stalled connection leave the UI 'running' forever.
  const watchdog = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('SIGNAL TIMEOUT - the pipeline took too long to respond. The server may be restarting; please try again.')), 90_000),
  )

  try {
    await Promise.race([readLoop, watchdog])
  } finally {
    reader.cancel().catch(() => { })
  }
  if (buffer.trim()) wrapped(JSON.parse(buffer) as StreamMessage)
  // If the server closed the stream without a result or error (e.g. it restarted
  // mid-request), surface that instead of silently leaving the UI stuck.
  if (!terminal) throw new Error('CONNECTION CLOSED - the answer never arrived (Railway may be restarting). Please try again.')
}

export async function streamTextQuery(query: string, onMessage: (message: StreamMessage) => void, signal?: AbortSignal) {
  return readNDJSON(await fetch('/api/query/stream', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
    body: JSON.stringify({ query }), signal,
  }), onMessage, signal)
}

export async function streamVoiceQuery(blob: Blob, onMessage: (message: StreamMessage) => void, signal?: AbortSignal) {
  const form = new FormData()
  const extension = blob.type.includes('ogg') ? 'ogg' : 'webm'
  form.append('audio', blob, `signal-recording.${extension}`)
  return readNDJSON(await fetch('/api/query/voice/stream', {
    method: 'POST', headers: { Accept: 'application/x-ndjson' }, body: form, signal,
  }), onMessage, signal)
}
