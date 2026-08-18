import { useCallback, useEffect, useRef, useState } from 'react'

export type RecorderState = 'idle' | 'requesting' | 'listening' | 'stopped' | 'error' | 'unsupported'

export function useVoiceRecorder() {
  const supported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'
  const [state, setState] = useState<RecorderState>(supported ? 'idle' : 'unsupported')
  const [duration, setDuration] = useState(0)
  const [waveform, setWaveform] = useState<number[]>(Array(28).fill(0.08))
  const [error, setError] = useState<string | null>(null)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const audioContext = useRef<AudioContext | null>(null)
  const animationFrame = useRef(0)
  const timer = useRef<number | null>(null)
  const chunks = useRef<Blob[]>([])
  const stopResolver = useRef<((blob: Blob) => void) | null>(null)

  const teardown = useCallback(() => {
    if (animationFrame.current) cancelAnimationFrame(animationFrame.current)
    if (timer.current) window.clearInterval(timer.current)
    stream.current?.getTracks().forEach(track => track.stop())
    void audioContext.current?.close()
    stream.current = null
    audioContext.current = null
    timer.current = null
  }, [])

  useEffect(() => teardown, [teardown])

  const start = useCallback(async () => {
    if (!supported) { setState('unsupported'); return }
    setState('requesting'); setError(null); setDuration(0); chunks.current = []
    try {
      const activeStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      stream.current = activeStream
      const preferred = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type))
      const recorder = new MediaRecorder(activeStream, preferred ? { mimeType: preferred } : undefined)
      mediaRecorder.current = recorder
      recorder.ondataavailable = event => { if (event.data.size) chunks.current.push(event.data) }
      recorder.onstop = () => {
        const blob = new Blob(chunks.current, { type: recorder.mimeType || 'audio/webm' })
        teardown(); setState('stopped'); stopResolver.current?.(blob); stopResolver.current = null
      }
      const context = new AudioContext()
      audioContext.current = context
      const analyser = context.createAnalyser(); analyser.fftSize = 256; analyser.smoothingTimeConstant = 0.72
      context.createMediaStreamSource(activeStream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      const draw = () => {
        analyser.getByteFrequencyData(data)
        const width = 28; const stride = Math.max(1, Math.floor(data.length / width))
        setWaveform(Array.from({ length: width }, (_, index) => Math.max(0.05, data[index * stride] / 255)))
        animationFrame.current = requestAnimationFrame(draw)
      }
      draw(); recorder.start(250); setState('listening')
      const began = performance.now()
      timer.current = window.setInterval(() => setDuration((performance.now() - began) / 1000), 100)
    } catch (cause) {
      teardown(); setState('error')
      const denied = cause instanceof DOMException && (cause.name === 'NotAllowedError' || cause.name === 'PermissionDeniedError')
      setError(denied ? 'Microphone permission was denied. Enable it or switch to text.' : 'The microphone could not be started.')
    }
  }, [supported, teardown])

  const stop = useCallback(() => new Promise<Blob>((resolve, reject) => {
    if (!mediaRecorder.current || mediaRecorder.current.state !== 'recording') { reject(new Error('No active recording')); return }
    stopResolver.current = resolve; mediaRecorder.current.stop()
  }), [])

  const cancel = useCallback(() => {
    stopResolver.current = null
    if (mediaRecorder.current?.state === 'recording') mediaRecorder.current.onstop = null
    mediaRecorder.current?.stop(); teardown(); chunks.current = []; setState('idle'); setDuration(0); setWaveform(Array(28).fill(0.08))
  }, [teardown])

  return { state, duration, waveform, error, start, stop, cancel }
}
