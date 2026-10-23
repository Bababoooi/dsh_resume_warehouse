/**
 * DSH host bundle for the local-first Resume Warehouse.
 *
 * It intentionally does almost nothing by itself: it exposes ONE tool that can
 * start / stop / inspect the Python app that lives in this same repository.
 * All resume data, PDFs and logs stay on this machine; the only outbound path
 * is the LLM call the user explicitly approves inside the app.
 */
import { spawn } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { isAbsolute, join, resolve } from 'node:path'

export const name = 'resume-warehouse'
export const inject = ['tools']

export const Config = {
  type: 'object',
  properties: {
    repoPath: {
      type: 'string',
      description:
        'Absolute path to the resume-warehouse checkout (the folder that contains server/server.py). Defaults to $DSH_RESUME_WAREHOUSE_DIR, then the current working directory.',
    },
    startTimeoutMs: {
      type: 'number',
      description: 'How long to wait for the app to answer /health after starting it. Default 30000.',
    },
  },
  additionalProperties: false,
}

const START_SCRIPT = join('skills', 'resume-warehouse', 'start.sh')
const STOP_SCRIPT = join('skills', 'resume-warehouse', 'stop.sh')
const PORT_FILE = join('data', 'runtime', 'app_port')

function fail(code, message) {
  return { action: 'error', ok: false, code, message }
}

function sleep(ms) {
  return new Promise((done) => setTimeout(done, ms))
}

/** Resolve + validate the checkout. Exported so tests can cover it without spawning. */
export function resolveRepo(config = {}, cwd = process.cwd(), env = process.env) {
  const raw = config.repoPath || env.DSH_RESUME_WAREHOUSE_DIR || cwd
  const repo = isAbsolute(raw) ? raw : resolve(cwd, raw)
  if (!existsSync(join(repo, 'server', 'server.py'))) {
    return { ok: false, message: `${repo} 里找不到 server/server.py，请把 repoPath 指向 resume-warehouse 目录` }
  }
  return { ok: true, repo }
}

/** Read the port the app wrote on startup. Pure I/O, no network. */
export function readPort(repo) {
  const file = join(repo, PORT_FILE)
  if (!existsSync(file)) return { ok: false, message: '还没启动过（缺少 data/runtime/app_port）' }
  try {
    const parsed = JSON.parse(readFileSync(file, 'utf8'))
    const port = Number(parsed.port)
    if (!Number.isInteger(port) || port <= 0 || port > 65535) {
      return { ok: false, message: `app_port 里的端口不可用：${JSON.stringify(parsed.port)}` }
    }
    return { ok: true, port, url: typeof parsed.url === 'string' ? parsed.url : `http://127.0.0.1:${port}`, pid: parsed.pid }
  } catch (error) {
    return { ok: false, message: `app_port 不是合法 JSON：${error.message}` }
  }
}

async function fetchJson(url, timeoutMs) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, { signal: controller.signal })
    const text = await response.text()
    let body = null
    try {
      body = JSON.parse(text)
    } catch {
      body = { raw: text.slice(0, 200) }
    }
    return { ok: response.ok, status: response.status, body }
  } catch (error) {
    return { ok: false, status: 0, body: { error: error.message } }
  } finally {
    clearTimeout(timer)
  }
}

/** Deps are injected so the contract test can run every action without touching the disk. */
export function createHandlers(deps = {}) {
  const spawnDetached = deps.spawnDetached || defaultSpawnDetached
  const runBash = deps.runBash || defaultRunBash
  const health = deps.health || fetchJson
  const waitMs = deps.waitMs || sleep
  const now = deps.now || Date.now

  return {
    async status(repo) {
      const portInfo = readPort(repo)
      if (!portInfo.ok) return fail('NOT_RUNNING', portInfo.message)
      const probe = await health(`${portInfo.url}/api/v1/health`, 5000)
      if (!probe.ok) {
        return fail('UNHEALTHY', `端口 ${portInfo.port} 有记录但 /health 不通（pid ${portInfo.pid ?? '未知'}）`)
      }
      const data = probe.body?.data || {}
      return {
        action: 'status',
        ok: true,
        url: portInfo.url,
        port: portInfo.port,
        pid: portInfo.pid,
        schemaVersion: data.db?.schema_version,
        llmReady: data.llm_ready,
        build: data.build?.id,
        message: '本机应用正在运行',
      }
    },

    async start(repo, config = {}, timeoutMs = 30000) {
      const portInfo = readPort(repo)
      if (portInfo.ok) {
        const probe = await health(`${portInfo.url}/api/v1/health`, 5000)
        if (probe.ok) {
          return { action: 'start', ok: true, alreadyRunning: true, url: portInfo.url, port: portInfo.port, message: '已经在运行，没有重复启动' }
        }
      }
      const script = join(repo, START_SCRIPT)
      if (!existsSync(script)) return fail('NO_SCRIPT', `缺少启动脚本：${script}`)
      const spawned = spawnDetached(script, repo)
      if (!spawned.ok) return fail('SPAWN_FAILED', spawned.message)

      const deadline = now() + timeoutMs
      while (now() < deadline) {
        await waitMs(1000)
        const fresh = readPort(repo)
        if (!fresh.ok) continue
        const probe = await health(`${fresh.url}/api/v1/health`, 3000)
        if (probe.ok) {
          return { action: 'start', ok: true, alreadyRunning: false, url: fresh.url, port: fresh.port, pid: fresh.pid, message: '已启动' }
        }
      }
      return fail('START_TIMEOUT', `等了 ${Math.round(timeoutMs / 1000)} 秒仍没有 /health，请查看 logs/ 与 data/runtime/app_port`)
    },

    async stop(repo) {
      const portInfo = readPort(repo)
      const script = join(repo, STOP_SCRIPT)
      if (!existsSync(script)) return fail('NO_SCRIPT', `缺少停止脚本：${script}`)
      const result = runBash(script, repo)
      if (!result.ok) return fail('STOP_FAILED', result.message)
      return {
        action: 'stop',
        ok: true,
        stoppedPort: portInfo.ok ? portInfo.port : null,
        message: '已停止（之前的端口记录保留在 data/runtime/app_port，下次启动会覆盖）',
      }
    },

    async open(repo) {
      const portInfo = readPort(repo)
      if (!portInfo.ok) return fail('NOT_RUNNING', `${portInfo.message}，先执行 start`)
      const probe = await health(`${portInfo.url}/api/v1/health`, 5000)
      if (!probe.ok) return fail('UNHEALTHY', '端口有记录但 /health 不通，先执行 start')
      return { action: 'open', ok: true, url: portInfo.url, port: portInfo.port, message: '在浏览器打开这个地址' }
    },
  }
}

function defaultSpawnDetached(script, cwd) {
  try {
    const child = spawn('bash', [script], { cwd, detached: true, stdio: 'ignore' })
    child.unref()
    return { ok: true }
  } catch (error) {
    return { ok: false, message: error.message }
  }
}

function defaultRunBash(script, cwd) {
  return new Promise((done) => {
    try {
      const child = spawn('bash', [script], { cwd, stdio: 'ignore' })
      const timer = setTimeout(() => {
        try {
          child.kill('SIGKILL')
        } catch {
          /* ignore */
        }
        done({ ok: false, message: '停止脚本 20 秒未结束，已强制结束子进程' })
      }, 20000)
      child.on('exit', (code) => {
        clearTimeout(timer)
        done(code === 0 ? { ok: true } : { ok: false, message: `stop.sh 退出码 ${code}` })
      })
      child.on('error', (error) => {
        clearTimeout(timer)
        done({ ok: false, message: error.message })
      })
    } catch (error) {
      done({ ok: false, message: error.message })
    }
  })
}

export function createTool(config = {}) {
  const handlers = createHandlers(config.deps || {})

  return {
    name: 'resume_warehouse',
    description:
      'Start, stop or inspect the local Resume Warehouse app running on this machine. Use it when the user asks to open their resume warehouse, check whether it is running, or shut it down. Nothing is uploaded; the app reads and writes only local files.',
    parameters: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['status', 'start', 'stop', 'open'],
          description: 'status = is it running and healthy; start = launch it and wait for /health; stop = shut it down; open = return the URL to open in a browser.',
        },
      },
      required: [],
      additionalProperties: false,
    },
    output: {
      schema: {
        type: 'object',
        properties: {
          action: { type: 'string' },
          ok: { type: 'boolean' },
          url: { type: 'string' },
          port: { type: 'number' },
          message: { type: 'string' },
        },
        required: ['action', 'ok', 'message'],
        additionalProperties: true,
      },
      render: (_args, value) => {
        if (!value) return '(no result)'
        const head = value.ok ? '✓' : '✗'
        const url = value.url ? ` ${value.url}` : ''
        return `${head} ${value.action}${url} — ${value.message ?? ''}`
      },
    },
    async execute(args = {}) {
      const action = args.action || 'status'
      const repoInfo = resolveRepo(config)
      if (!repoInfo.ok) return fail('NO_REPO', repoInfo.message)
      if (!(action in handlers)) return fail('BAD_ACTION', `不认识的动作 ${action}`)
      const timeoutMs = Number(config.startTimeoutMs) > 0 ? Number(config.startTimeoutMs) : 30000
      return handlers[action](repoInfo.repo, config, timeoutMs)
    },
  }
}

export function apply(ctx, config = {}) {
  const tool = createTool(config)
  ctx.effect(() => ctx.tools.register(tool))
}
