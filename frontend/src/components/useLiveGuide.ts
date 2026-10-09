import { useCallback, useEffect, useRef, useState } from 'react';
import { caseAccessToken } from '../api/client';

export type VoiceState = 'Idle' | 'Connecting' | 'Listening' | 'Thinking' | 'Speaking' | 'Disconnected';

function pcm16(input: Float32Array, inputRate: number): ArrayBuffer {
  const ratio = inputRate / 16000;
  const count = Math.floor(input.length / ratio);
  const buffer = new ArrayBuffer(count * 2);
  const output = new DataView(buffer);
  for (let i = 0; i < count; i++) {
    const sample = Math.max(-1, Math.min(1, input[Math.floor(i * ratio)]));
    output.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return buffer;
}

export function useLiveGuide(caseId: string, onUpdate: () => void) {
  const [available, setAvailable] = useState(false);
  const [state, setState] = useState<VoiceState>('Idle');
  const [error, setError] = useState('');
  const [transcript, setTranscript] = useState('');
  const ws = useRef<WebSocket | null>(null);
  const mic = useRef<MediaStream | null>(null);
  const inputContext = useRef<AudioContext | null>(null);
  const outputContext = useRef<AudioContext | null>(null);
  const processor = useRef<ScriptProcessorNode | null>(null);
  const nextPlayTime = useRef(0);
  const attempt = useRef(0);

  useEffect(() => {
    fetch('/api/guide/capabilities').then(response => response.json())
      .then(body => setAvailable(Boolean(body.data?.voice_available)))
      .catch(() => setAvailable(false));
  }, []);

  const stop = useCallback(() => {
    attempt.current += 1;
    processor.current?.disconnect(); processor.current = null;
    mic.current?.getTracks().forEach(track => track.stop()); mic.current = null;
    void inputContext.current?.close(); inputContext.current = null;
    void outputContext.current?.close(); outputContext.current = null;
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify({ event: 'stop' }));
    ws.current?.close(); ws.current = null;
    setState('Idle');
  }, []);

  useEffect(() => () => stop(), [stop]);

  const playAudio = useCallback((encoded: string) => {
    const context = outputContext.current;
    if (!context) return;
    const raw = atob(encoded);
    const audio = context.createBuffer(1, Math.floor(raw.length / 2), 24000);
    const samples = audio.getChannelData(0);
    for (let i = 0; i < samples.length; i++) {
      const value = raw.charCodeAt(i * 2) | (raw.charCodeAt(i * 2 + 1) << 8);
      samples[i] = (value > 32767 ? value - 65536 : value) / 32768;
    }
    const source = context.createBufferSource(); source.buffer = audio; source.connect(context.destination);
    nextPlayTime.current = Math.max(nextPlayTime.current, context.currentTime);
    source.start(nextPlayTime.current);
    nextPlayTime.current += audio.duration;
  }, []);

  const start = useCallback(async () => {
    if (!caseId || !available || ws.current) return;
    setError(''); setTranscript('');
    const token = caseAccessToken(caseId);
    if (!token) { setState('Disconnected'); setError('This trip has no saved access token in this browser. Open a trip created here.'); return; }
    const currentAttempt = ++attempt.current;
    setState('Connecting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (attempt.current !== currentAttempt) { stream.getTracks().forEach(track => track.stop()); return; }
      mic.current = stream;
      inputContext.current = new AudioContext();
      outputContext.current = new AudioContext();
      await outputContext.current.resume();
      if (attempt.current !== currentAttempt) return;
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/cases/${encodeURIComponent(caseId)}/guide/live`,
        [`case-token.${token}`]);
      ws.current = socket;
      socket.onmessage = event => {
        const message = JSON.parse(event.data) as { event: string; data?: string; text?: string; message?: string; error?: string; saved?: boolean; remaining?: string[] };
        if (message.event === 'connected') {
          const context = inputContext.current;
          if (!context || !mic.current) return;
          const source = context.createMediaStreamSource(mic.current);
          const node = context.createScriptProcessor(2048, 1, 1);
          node.onaudioprocess = audioEvent => {
            if (socket.readyState === WebSocket.OPEN) socket.send(pcm16(audioEvent.inputBuffer.getChannelData(0), context.sampleRate));
          };
          source.connect(node); node.connect(context.destination); processor.current = node;
          setState('Listening');
        } else if (message.event === 'heard') { setTranscript(message.text ?? ''); setState('Thinking'); onUpdate(); }
        else if (message.event === 'said') { setTranscript(message.text ?? ''); onUpdate(); }
        else if (message.event === 'audio' && message.data) { setState('Speaking'); playAudio(message.data); }
        else if (message.event === 'turn_complete') { setState('Listening'); }
        else if (message.event === 'proposal') { onUpdate(); }
        else if (message.event === 'clarification') { if (message.error) setError(message.error); else if (message.saved) setTranscript('Trip details saved. Planning continues.'); else if (message.remaining) setTranscript(`Still needed: ${message.remaining.join(', ')}`); onUpdate(); }
        else if (message.event === 'revision_unavailable') { setError(message.message ?? 'A revised draft is unavailable'); }
        else if (message.event === 'error') { setError(message.message ?? 'Live voice is unavailable'); setState('Disconnected'); }
      };
      socket.onerror = () => { if (ws.current === socket) { setError('The voice connection could not open. Check the WebSocket proxy and the site address, then retry. The text guide remains available.'); setState('Disconnected'); } };
      socket.onclose = event => { if (ws.current === socket) { ws.current = null; processor.current?.disconnect(); processor.current = null;
        mic.current?.getTracks().forEach(track => track.stop()); mic.current = null;
        void inputContext.current?.close(); inputContext.current = null;
        void outputContext.current?.close(); outputContext.current = null;
        if (event.code === 1008) setError('Voice access was declined for this trip or site address. Reopen the trip in this browser, then retry.');
        else if (event.code === 1013) setError('Gemini Live is unavailable on the server right now. The text guide remains available.');
        else setError(previous => previous || 'The voice session ended. You can retry or use the text guide.');
        setState('Disconnected'); } };
    } catch (cause) {
      stop(); setState('Disconnected');
      setError(cause instanceof Error ? cause.message : 'Microphone access is unavailable');
    }
  }, [available, caseId, onUpdate, playAudio, stop]);

  return { available, state, error, transcript, start, stop };
}
