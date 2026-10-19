#!/usr/bin/env node
/**
 * coros-mcp-proxy —— 修掉 COROS 官方 MCP 的 JSON Schema 缺陷，顺带做透传。
 *
 * 背景：COROS 服务端把 `$defs` 写在子 schema 内部，`$ref` 却写成 `#/$defs/Section`
 * （`#` 指文档根）。根上没有 `$defs`，于是 DeepSeek API 在每次请求校验整批
 * tools[].function.parameters 时直接 400 —— 表现为"整轮对话失败"，而不是某个工具
 * 不可用。本代理只做一件事：把 `tools/list` 响应里嵌套的 `$defs` 提升到 schema 根。
 *
 * 用法：
 *   node coros-mcp-proxy.js <mcp-url> [传给 mcp-remote 的额外参数...]
 *
 *   node coros-mcp-proxy.js https://mcpcn.coros.com/mcp
 *   node coros-mcp-proxy.js https://mcpcn.coros.com/mcp --transport http-only
 *
 * 环境变量：
 *   MCP_REMOTE_NPX_CLI  手动指定 npx-cli.js 路径（自动探测失败时用）
 *   MCP_REMOTE_SPEC     覆盖 mcp-remote 版本，默认 mcp-remote@0.14.3
 *
 * 设计约束（改代码前先读）：
 *   1. 只拦 `tools/list` 的响应，其余消息逐字节透传 —— 尤其 `tools/call` 的参数体
 *      里全是用户数据，不该被碰。
 *   2. 同名 `$defs` 冲突时改名（`Name$nested`）而不是覆盖，否则两个不同结构会被
 *      折叠成一个，静默改坏语义。
 *   3. 不存 token、不联网、不落盘；OAuth 完全交给 mcp-remote。
 *   4. 不修 `outputSchema` —— dsh-mcp-client 对它能解析则用、不能解析则回退
 *      JsonValue，不会导致请求失败。
 */
'use strict';

const { spawn } = require('node:child_process');
const { existsSync } = require('node:fs');
const { join, delimiter } = require('node:path');

const MCP_REMOTE_SPEC = process.env.MCP_REMOTE_SPEC || 'mcp-remote@0.14.3';

const log = (message) => process.stderr.write('[coros-proxy] ' + message + '\n');

/**
 * 找到 npx-cli.js，用 `node npx-cli.js` 启动。
 *
 * 为什么不直接 spawn('npx')：Windows 上 node_modules/.bin 里同时有 `npx`（无扩展名
 * 的 sh 脚本）、`npx.cmd`、`npx.ps1`；而 Node 在 Windows 上不允许不带 shell 直接执行
 * `.cmd`。指定 npx-cli.js 是唯一在两种平台都稳的写法。
 */
function resolveNpxCli() {
  if (process.env.MCP_REMOTE_NPX_CLI) return process.env.MCP_REMOTE_NPX_CLI;

  const candidates = [];
  for (const dir of (process.env.PATH || '').split(delimiter)) {
    if (!dir) continue;
    candidates.push(join(dir, 'node_modules', 'npm', 'bin', 'npx-cli.js'));
    // npm 装在 <prefix>/bin 时，npx-cli.js 在 <prefix>/lib/node_modules/npm/bin
    candidates.push(join(dir, '..', 'lib', 'node_modules', 'npm', 'bin', 'npx-cli.js'));
  }
  if (process.env.npm_config_prefix) {
    candidates.push(join(process.env.npm_config_prefix, 'node_modules', 'npm', 'bin', 'npx-cli.js'));
  }
  for (const candidate of candidates) {
    try {
      if (existsSync(candidate)) return candidate;
    } catch {
      /* ignore */
    }
  }
  return null;
}

/**
 * 把嵌套的 `$defs` 提升到 schema 根。
 * @param {object} schema 会被就地修改
 * @param {string} toolName 仅用于日志
 */
function hoistDefs(schema, toolName) {
  if (!schema || typeof schema !== 'object') return 0;

  const hoisted = Object.create(null);
  let count = 0;

  function walk(node, isRoot) {
    if (Array.isArray(node)) {
      for (const item of node) walk(item, false);
      return;
    }
    if (!node || typeof node !== 'object') return;

    for (const key of Object.keys(node)) {
      const value = node[key];
      if (key === '$defs' && !isRoot) {
        for (const [name, def] of Object.entries(value)) {
          if (!(name in hoisted)) {
            hoisted[name] = def;
            count += 1;
          } else if (JSON.stringify(hoisted[name]) !== JSON.stringify(def)) {
            let alt = name + '$nested';
            for (let i = 2; alt in hoisted; i += 1) alt = name + '$nested' + i;
            hoisted[alt] = def;
            count += 1;
            log(toolName + ': $defs name collision "' + name + '" -> "' + alt + '"');
          }
        }
        delete node[key];
      } else {
        walk(value, false);
      }
    }
  }

  walk(schema, true);

  if (count > 0) {
    schema.$defs = Object.assign({}, schema.$defs || {}, hoisted);
  }
  return count;
}

/** 若这条消息是 `tools/list` 响应，就地修 schema。 */
function normalizeResponse(message) {
  const tools = message && message.result && Array.isArray(message.result.tools)
    ? message.result.tools
    : null;
  if (!tools) return;

  for (const tool of tools) {
    if (!tool || !tool.inputSchema) continue;
    const fixed = hoistDefs(tool.inputSchema, tool.name);
    if (fixed > 0) log('hoisted ' + fixed + ' $defs for tool "' + tool.name + '"');
  }
}

function main() {
  const url = process.argv[2];
  const extraArgs = process.argv.slice(3);

  if (!url || url === '-h' || url === '--help') {
    process.stderr.write(
      'usage: node coros-mcp-proxy.js <mcp-url> [extra mcp-remote args...]\n' +
        'example: node coros-mcp-proxy.js https://mcpcn.coros.com/mcp\n'
    );
    process.exit(url ? 0 : 2);
  }

  const npxCli = resolveNpxCli();
  const child = npxCli
    ? spawn(process.execPath, [npxCli, '-y', MCP_REMOTE_SPEC, url, ...extraArgs], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: process.env,
        windowsHide: true,
      })
    : spawn(
        process.platform === 'win32' ? 'npx.cmd' : 'npx',
        ['-y', MCP_REMOTE_SPEC, url, ...extraArgs],
        {
          stdio: ['pipe', 'pipe', 'pipe'],
          env: process.env,
          windowsHide: true,
          shell: process.platform === 'win32',
        }
      );

  if (!npxCli) {
    log('npx-cli.js not found on PATH, falling back to shell npx (set MCP_REMOTE_NPX_CLI to pin it)');
  }

  // DSH -> mcp-remote：原样转发
  process.stdin.pipe(child.stdin);
  process.stdin.on('end', () => child.stdin.end());

  // mcp-remote -> DSH：逐行解析，只改 tools/list
  let outBuffer = '';
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (chunk) => {
    outBuffer += chunk;
    let index;
    while ((index = outBuffer.indexOf('\n')) >= 0) {
      const line = outBuffer.slice(0, index);
      outBuffer = outBuffer.slice(index + 1);
      const trimmed = line.trim();
      if (!trimmed) {
        process.stdout.write('\n');
        continue;
      }
      try {
        const message = JSON.parse(trimmed);
        normalizeResponse(message);
        process.stdout.write(JSON.stringify(message) + '\n');
      } catch {
        process.stdout.write(line + '\n');
      }
    }
  });

  child.stderr.on('data', (chunk) => process.stderr.write(chunk));

  child.on('error', (error) => {
    log('failed to start mcp-remote: ' + error.message);
    process.exit(1);
  });

  child.on('exit', (code, signal) => {
    if (signal) log('mcp-remote exited on signal ' + signal);
    process.exit(code === null ? 0 : code);
  });
}

// 允许被测试文件 require 而不启动代理
module.exports = { hoistDefs, normalizeResponse, resolveNpxCli };

if (require.main === module) main();
