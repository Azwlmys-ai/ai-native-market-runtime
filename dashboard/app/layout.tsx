import type { Metadata } from 'next'
import './globals.css'
import { ExecutiveModeProvider } from './contexts/ExecutiveModeContext'

export const metadata: Metadata = {
  title: 'Polymarket AI Executive Command Center',
  description: 'AI Agent Executive Command Center — Enterprise Multi-Agent Runtime Intelligence System',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark h-full">
      <body className="font-mono h-full bg-[#0f1d3a] text-slate-100 antialiased">
        <ExecutiveModeProvider>
          {children}
        </ExecutiveModeProvider>
      </body>
    </html>
  )
}
