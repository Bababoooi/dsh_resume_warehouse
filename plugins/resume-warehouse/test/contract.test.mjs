import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

import { apply, createTool, name as pluginName, resolveRepo } from '../index.js'

const here = fileURLToPath(new URL('..', import.meta.url))
const manifest = JSON.parse(readFileSync(join(here, 'package.json'), 'utf8'))

function fakeRepo({ withServer = true, withPort = null } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'rw-plugin-'))
  if (withServer) {
    mkdirSync(join(dir, 'server'), { recursive: true })
    writeFileSync(join(dir, 'server', 'server.py'), '# stub\n')
  }
  mkdirSync(join(dir, 'data', 'runtime'), { recursive: true })
  mkdirSync(join(dir, 'skills', 'resume-warehouse'), { recursive: true })
  for (const script of ['start.sh', 'stop.sh']) {
    writeFileSync(join(dir, 'skills', 'resume-warehouse', script), '#!/usr/bin/env bash\nexit 0\n')
  }
  if (withPort) writeFileSync(join(dir, 'data', 'runtime', 'app_port'), withPort)
  return dir
}

test('manifest points at this bundle and ships every runtime asset', () => {
  assert.equal(manifest.name, 'dsh-plugin-resume-warehouse')
  assert.equal(manifest.type, 'module')
  assert.equal(manifest.dsh?.bundle?.patch, './cordis.patch.yml')
  assert.ok(manifest.engines?.dsh, 'engines.dsh is how the marketplace judges compatibility')
  for (const key of ['index.js', 'cordis.patch.yml', 'icon.svg', 'README.md']) {
    assert.ok(manifest.files.includes(key), `${key} must be published`)
  }
  assert.ok(manifest.exports['./locale/*.json'], 'locale must be exported for host resolution')
  assert.ok(manifest.exports['./icon'])
})

test('patch inserts exactly one row whose name matches the package', () => {
  const patch = readFileSync(join(here, 'cordis.patch.yml'), 'utf8')
  const inserts = [...patch.matchAll(/id:\s*([\w-]+)/g)].map((m) => m[1])
  const names = [...patch.matchAll(/name:\s*'?"?([\w-]+)'?"?/g)].map((m) => m[1])
  assert.deepEqual(inserts, ['resume-warehouse'])
  assert.deepEqual(names, [manifest.name])
})

test('locales carry marketplace metadata in both languages', () => {
  for (const lang of ['en', 'zh']) {
    const meta = JSON.parse(readFileSync(join(here, 'locale', `${lang}.json`), 'utf8')).meta
    assert.ok(meta.title.length > 2, `${lang} title`)
    assert.ok(meta.description.length > 40, `${lang} description must explain what it does`)
  }
})

test('icon is a small inline svg', () => {
  const file = join(here, 'icon.svg')
  assert.ok(statSync(file).size < 256 * 1024)
  assert.match(readFileSync(file, 'utf8').trim(), /^<svg[\s>]/)
})

test('resolveRepo rejects a folder without server/server.py and accepts a real one', () => {
  assert.equal(resolveRepo({ repoPath: fakeRepo({ withServer: false }) }).ok, false)
  const good = fakeRepo()
  const resolved = resolveRepo({ repoPath: good })
  assert.equal(resolved.ok, true)
  assert.equal(resolved.repo, good)
})

test('tool definition satisfies the host Tool contract', () => {
  const tool = createTool({})
  assert.equal(tool.name, 'resume_warehouse')
  assert.ok(tool.description.length > 40)
  assert.deepEqual(tool.parameters.properties.action.enum, ['status', 'start', 'stop', 'open'])
  assert.equal(tool.parameters.required.length, 0)
  assert.ok(tool.output?.schema, 'output.schema is required')
  const rendered = tool.output.render({ action: 'status' }, { action: 'status', ok: true, url: 'http://127.0.0.1:8765', message: '本机应用正在运行' })
  assert.match(rendered, /^✓ status http:\/\/127\.0\.0\.1:8765/)
})

test('apply registers one tool and returns a disposer through ctx.effect', () => {
  const registered = []
  const disposed = []
  const ctx = {
    effect(fn) {
      const disposer = fn()
      disposed.push(typeof disposer)
      return disposer
    },
    tools: {
      register(definition) {
        registered.push(definition)
        return () => registered.pop()
      },
    },
  }
  apply(ctx, {})
  assert.equal(registered.length, 1)
  assert.equal(registered[0].name, 'resume_warehouse')
  assert.deepEqual(disposed, ['function'], 'the disposer must be handed back to ctx.effect')
})

test('status without a port file is a clean NOT_RUNNING, not a crash', async () => {
  const tool = createTool({ repoPath: fakeRepo() })
  const result = await tool.execute({ action: 'status' })
  assert.equal(result.ok, false)
  assert.equal(result.code, 'NOT_RUNNING')
})

test('a recorded port whose /health fails is UNHEALTHY', async () => {
  const repo = fakeRepo({ withPort: JSON.stringify({ port: 8765, url: 'http://127.0.0.1:8765', pid: 42 }) })
  const tool = createTool({ repoPath: repo, deps: { health: async () => ({ ok: false, status: 0, body: {} }) } })
  const result = await tool.execute({ action: 'status' })
  assert.equal(result.ok, false)
  assert.equal(result.code, 'UNHEALTHY')
})

test('start never spawns twice when /health already answers', async () => {
  let spawned = 0
  const repo = fakeRepo({ withPort: JSON.stringify({ port: 8765, url: 'http://127.0.0.1:8765', pid: 42 }) })
  const tool = createTool({
    repoPath: repo,
    deps: {
      spawnDetached: () => {
        spawned += 1
        return { ok: true }
      },
      health: async () => ({ ok: true, status: 200, body: { data: { db: { schema_version: 13 }, llm_ready: true, build: { id: 'test' } } } }),
    },
  })
  const result = await tool.execute({ action: 'start' })
  assert.equal(result.ok, true)
  assert.equal(result.alreadyRunning, true)
  assert.equal(spawned, 0)
})

test('status reports real health fields when the app answers', async () => {
  const repo = fakeRepo({ withPort: JSON.stringify({ port: 8770, url: 'http://127.0.0.1:8770', pid: 7 }) })
  const tool = createTool({
    repoPath: repo,
    deps: {
      health: async () => ({ ok: true, status: 200, body: { data: { db: { schema_version: 13 }, llm_ready: false, build: { id: 'abc' } } } }),
    },
  })
  const result = await tool.execute({ action: 'status' })
  assert.equal(result.ok, true)
  assert.equal(result.port, 8770)
  assert.equal(result.schemaVersion, 13)
  assert.equal(result.build, 'abc')
})

test('stop and open go through the injected seams', async () => {
  const repo = fakeRepo({ withPort: JSON.stringify({ port: 8765, url: 'http://127.0.0.1:8765', pid: 42 }) })
  const tool = createTool({
    repoPath: repo,
    deps: {
      runBash: () => ({ ok: true }),
      health: async () => ({ ok: true, status: 200, body: { data: {} } }),
    },
  })
  const stopped = await tool.execute({ action: 'stop' })
  assert.equal(stopped.ok, true)
  assert.equal(stopped.stoppedPort, 8765)
  const opened = await tool.execute({ action: 'open' })
  assert.equal(opened.url, 'http://127.0.0.1:8765')
})

test('unknown action and missing repo fail loudly', async () => {
  const bad = await createTool({ repoPath: fakeRepo() }).execute({ action: 'rebuild' })
  assert.equal(bad.code, 'BAD_ACTION')
  const noRepo = await createTool({ repoPath: join(tmpdir(), 'definitely-not-here-rw') }).execute({ action: 'status' })
  assert.equal(noRepo.code, 'NO_REPO')
  assert.equal(pluginName, 'resume-warehouse')
})
