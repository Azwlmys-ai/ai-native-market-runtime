'use client'

import { useSyncExternalStore } from 'react'

function useMounted() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  )
}

export default function ClockDisplay({
  presentationMode = false,
}: {
  presentationMode?: boolean
}) {
  const mounted = useMounted()

  if (!mounted) {
    return null
  }

  return (
    <span
      className={`font-mono text-slate-600 ${
        presentationMode ? 'text-sm font-bold text-cyan-400' : 'text-[10px]'
      }`}
    >
      {new Date().toLocaleTimeString('en-US', { hour12: false })}
    </span>
  )
}