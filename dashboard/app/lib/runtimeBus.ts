// ── Runtime Event Bus ───────────────────────────────────
// Lightweight pub/sub bus built on EventTarget.
// Shared singleton — no React Context needed.
// Designed to be smoothly replaceable with WebSocket.

import type { RuntimeStreamEvent } from '@/app/types/runtime'

type EventCallback = (event: RuntimeStreamEvent) => void

class RuntimeBus {
  private target = new EventTarget()
  private listeners = new WeakMap<EventCallback, (e: Event) => void>()
  private events: RuntimeStreamEvent[] = []
  private maxEvents = 200
  private snapshotSubs = new Set<() => void>()

  subscribe(callback: EventCallback): () => void {
    const handler = (e: Event) => {
      callback((e as CustomEvent<RuntimeStreamEvent>).detail)
    }
    this.target.addEventListener('runtime', handler)
    this.listeners.set(callback, handler)
    return () => {
      this.target.removeEventListener('runtime', handler)
      this.listeners.delete(callback)
    }
  }

  emit(event: RuntimeStreamEvent) {
    this.events = [...this.events, event].slice(-this.maxEvents)
    this.target.dispatchEvent(new CustomEvent('runtime', { detail: event }))
    this.snapshotSubs.forEach(fn => fn())
  }

  getSnapshot(): RuntimeStreamEvent[] {
    return this.events
  }

  subscribeSnapshot(callback: () => void): () => void {
    this.snapshotSubs.add(callback)
    return () => this.snapshotSubs.delete(callback)
  }
}

export const runtimeBus = new RuntimeBus()