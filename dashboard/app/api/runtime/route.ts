import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { NextResponse } from 'next/server'

// Legacy API: retained during P3 while the dashboard converges on /api/visualization-state.
const DATA_DIR = '/Users/libo/.hermes/polymarket_arbitrage/data'
const LOGS_DIR = '/Users/libo/.hermes/polymarket_arbitrage/logs'

function safeReadJson(filePath: string): unknown | null {
  try {
    const raw = readFileSync(filePath, 'utf-8')
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function getLatestOrchestratorLog(): { content: string | null; error: string | null } {
  try {
    if (!existsSync(LOGS_DIR)) {
      return { content: null, error: 'Logs directory not found' }
    }
    const files = readdirSync(LOGS_DIR)
      .filter((f) => f.startsWith('orchestrator_') && f.endsWith('.log'))
      .sort()
      .reverse()

    if (files.length === 0) {
      return { content: null, error: 'No orchestrator log found' }
    }

    const latestFile = files[0]
    const filePath = join(LOGS_DIR, latestFile)
    const raw = readFileSync(filePath, 'utf-8')
    const lines = raw.split('\n').filter(Boolean)
    // Return last 80 lines
    const tail = lines.slice(-80).join('\n')

    return { content: tail, error: null }
  } catch (e) {
    return { content: null, error: String(e) }
  }
}

export async function GET() {
  // ── Execution results ──
  let executionResults = null
  let executionError: string | null = null
  try {
    const data = safeReadJson(join(DATA_DIR, 'execution_results.json'))
    executionResults = data
  } catch (e) {
    executionError = String(e)
  }

  // ── Approved signals ──
  let approvedSignals = null
  let approvedSignalsError: string | null = null
  try {
    const data = safeReadJson(join(DATA_DIR, 'approved_signals.json'))
    approvedSignals = data
  } catch (e) {
    approvedSignalsError = String(e)
  }

  // ── Agent M learned rules ──
  let agentMRules = null
  let agentMRulesError: string | null = null
  try {
    const data = safeReadJson(join(DATA_DIR, 'agent_m_learned_rules.json'))
    agentMRules = data
  } catch (e) {
    agentMRulesError = String(e)
  }

  // ── Orchestrator log ──
  const { content: orchestratorLog, error: orchestratorLogError } =
    getLatestOrchestratorLog()

  return NextResponse.json({
    executionResults,
    executionError,
    approvedSignals,
    approvedSignalsError,
    agentMRules,
    agentMRulesError,
    orchestratorLog,
    orchestratorLogError,
  })
}
