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

async function readNDJSON(response: Response, onMessage: (message: StreamMessage) => void) {
  await checked(response)
  if (!response.body) throw new Error('Streaming response is not supported by this browser')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) if (line.trim()) onMessage(JSON.parse(line) as StreamMessage)
    if (done) break
  }
  if (buffer.trim()) onMessage(JSON.parse(buffer) as StreamMessage)
}

export async function streamTextQuery(query: string, onMessage: (message: StreamMessage) => void, signal?: AbortSignal) {
  return readNDJSON(await fetch('/api/query/stream', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
    body: JSON.stringify({ query }), signal,
  }), onMessage)
}

export async function streamVoiceQuery(blob: Blob, onMessage: (message: StreamMessage) => void, signal?: AbortSignal) {
  const form = new FormData()
  const extension = blob.type.includes('ogg') ? 'ogg' : 'webm'
  form.append('audio', blob, `signal-recording.${extension}`)
  return readNDJSON(await fetch('/api/query/voice/stream', {
    method: 'POST', headers: { Accept: 'application/x-ndjson' }, body: form, signal,
  }), onMessage)
}
