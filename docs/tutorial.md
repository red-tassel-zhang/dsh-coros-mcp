# 把 COROS 官方 MCP 接进 DeepSeek Harness —— 分步实录

> 环境：Windows 11 · DSH **0.2.1-rc.2**（桌面端）· `dsh-mcp-client` **0.2.1-rc.2** · Node **v24**
> 目标 profile：`<DSH_HOME>/profiles/desktop`
> 结果：`mcp__coros__*` 三十余个原生工具可用，读写均验证通过

---

## 0. 一句话结论

COROS 官方只提供 **OAuth 2.0 保护的远程 MCP**（`https://mcpcn.coros.com/mcp`），而 DSH 的 `dsh-mcp-client` 只支持
`stdio` 与 `streamable-http`（后者只能加静态 `headers`，**没有 OAuth 授权流程**）。
所以直连必然卡在鉴权上。可行的拼装是**三层**：

```
DSH 插件树
  └─ dsh-mcp-client（stdio 行，serverName: coros）
       └─ node coros-mcp-proxy.js      ← 我们加的：修 schema 缺陷 + 透传
            └─ npx mcp-remote@0.14.3   ← 社区桥：负责 OAuth 登录/刷新/token 缓存
                 └─ https://mcpcn.coros.com/mcp   ← COROS 官方远程 MCP
```

三层的分工是**不可合并**的：`mcp-remote` 解决"**怎么登录**"，本地代理解决"**COROS 的 schema 不合规**"。

---

## 1. 为什么不能只用 mcp-remote（这是本文的核心）

第一版配置**只挂了 mcp-remote**，重启后工具确实出现了，但紧接着**整个回合直接崩**：

```
本轮运行失败 Invalid schema for function 'mcp__coros__createScheduledWorkout':
Pointer '/$defs/Section' does not exist (request_id: <uuid>)
```

认知要点（很多人会误判为"某个工具不能用"）：

- **不是某个工具失败，是整个请求被拒。** DeepSeek API 在每次请求时校验**整批** `tools[].function.parameters`，
  只要有一个函数的 JSON Schema 解析不了，**整轮对话 400**，连寒暄都发不出去。
- 你感觉到的现象是"一开 COROS 就挂"，其实是**任何一个坏 schema 都会让这一轮全部失败**。

### 根因

COROS 服务端在 6 个工具的 `inputSchema` 里这样写（`refs=2 $defs=3`）：

```jsonc
{
  "type": "object",
  "properties": {
    "course": {
      "$defs": { "Section": { /* ... */ } },   // ← $defs 嵌在子 schema 内部
      "properties": {
        "sections": { "items": { "$ref": "#/$defs/Section" } }   // ← 却按"文档根"去指
      }
    }
  }
}
```

`#/$defs/Section` 里的 `#` 表示**文档根**，但根上并没有 `$defs`，所以指针解析失败。合规写法是把 `$defs` 放在 schema 根。

受影响的 6 个工具（全是写操作，读操作都正常）：

| 工具 | 用途 |
|---|---|
| `createScheduledWorkout` | 在某天新建课表 |
| `updateScheduledWorkout` | 改某天的独立课表 |
| `createTrainingPlan` | 新建训练计划 |
| `updateTrainingPlan` | 改训练计划 |
| `createSingleWorkout` | 新建课表模板（库） |
| `updateWorkoutDetails` | 改课表模板（库） |

> 这也解释了为什么"读数据一直好好的，一做课表就炸"。

---

## 2. 准备工作

### 2.1 确认版本与 profile

```powershell
# DSH 版本（桌面端）
(Get-Item '<DSH 安装目录>\DeepSeek Harness.exe').VersionInfo.FileVersion
node --version
$prof = "$env:USERPROFILE\.dsh\profiles\desktop"
```

`dsh-mcp-client` 是**宿主内置**的，不需要 `pnpm add`。想确认版本：

```powershell
# 注意：asar 是单文件归档，不能直接用 rg 搜，得先解包
node -e "console.log(require('<DSH 安装目录>/resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-mcp-client/package.json').version)"
```

> 解包方式：用 `npx asar extract app.asar out`（或任何 asar 工具），之后就能读到 `README.zh.md` 与 `lib/index.js`。

### 2.2 先读官方字段表，别猜配置

`dsh-mcp-client` 的 `README.zh.md` 里有一张完整字段表，关键几项：

| 字段 | 默认 | 含义 |
|---|---|---|
| `transport` | 必填 | `stdio` / `streamable-http` |
| `serverName` | 必填 | 工具命名空间，`[A-Za-z0-9_-]{1,32}`；工具名变成 `mcp__<serverName>__<tool>` |
| `command`/`args`/`env`/`cwd` | — | stdio 专用 |
| `url`/`headers` | — | streamable-http 专用（**只支持静态头，没有 OAuth**） |
| `toolCallTimeoutMs` | `60000` | 单次 `tools/call` 超时 |
| `failOnStartupError` | `false` | 连不上时是否拒绝插件激活（默认 `false` ＝ harness 照常启动，只是工具不出现） |

**这张表里的 `headers` 只有静态值，就是"必须上 mcp-remote"的官方依据。**

---

## 3. 分步实施

### 步骤 A：先脱离 DSH，单独验证 OAuth 能通

**不要**一上来就改配置——先把鉴权这个变量单独钉死。

```powershell
npx -y mcp-remote@0.14.3 https://mcpcn.coros.com/mcp
```

首次会打开浏览器让你登录 COROS。成功时 stderr 会出现：

```
Discovered authorization server: https://mcpcn.coros.com
Connecting to remote server: https://mcpcn.coros.com/mcp
Using transport strategy: http-first
Connected to remote server using StreamableHTTPClientTransport
Proxy established successfully between local STDIO and remote StreamableHTTPClientTransport
```

登录态落在：

```
~/.mcp-auth/mcp-remote-v1/<url-hash>_tokens.json
~/.mcp-auth/mcp-remote-v1/<url-hash>_client_info.json
```

token 元数据里应有 `scope = mcp.tools openid offline_access`、`expires_in` 约 30 天、以及 `refresh_token`。
**带 `offline_access` 意味着过期能自动续，不用天天登录。**

> ⚠️ 两个 token 仓库别搞混：
> - `~/.mcp-auth/` —— **mcp-remote 用**（本文链路走这个）
> - `~/.coros-mcp-skill-gateway-ts/<region>/` —— **`coros-mcp` 这个 CLI 用**（另一套，互相不通用）
>
> 所以"CLI 登录过了"并不等于"mcp-remote 登录过了"。

**区域**：如果 `https://mcp.coros.com/mcp` 解析不出区域，直接用分区 issuer：
`https://mcpcn.coros.com/mcp`（中国）/ `mcpeu` / `mcpus`。

### 步骤 B：写本地代理

文件：`coros-mcp-proxy.js`（本仓库自带，零依赖）。作用：**只拦 `tools/list` 的响应**，
把嵌套的 `$defs` 提升到根；其余消息逐字节透传。

完整代码见 [`coros-mcp-proxy.js`](../coros-mcp-proxy.js)，这里只说设计要点（改代码前先看这几条）：

1. **`spawn(process.execPath, [npxCli, ...])` 而不是 `spawn('npx')`。**
   Windows 上 `node_modules/.bin` 里同时有 `npx`（无扩展名的 sh 脚本）、`npx.cmd`、`npx.ps1`；
   直接 `spawn('npx')` 可能命中那个无扩展名文件而 ENOENT/EINVAL，而 Node 又不允许不带 shell 执行 `.cmd`。
   用 `node + npx-cli.js` 是唯一在两种平台都稳的写法。
2. **只处理 `tools/list`，别碰 `tools/call`。** 写操作的参数体里有大量用户数据，透传最安全。
3. **同名 `$defs` 冲突时改名而不是覆盖**，否则两个不同结构会被折叠成一个，静默改坏语义。
4. 代理本身不存 token、不联网，**登录态始终由 mcp-remote 管**。

### 步骤 C：写入 profile 的 patch 层

DSH 的插件树是"bundle 层 → `cordis.patch.yml` 层"叠加，**你自己的改动永远写在后者**。

文件：`<DSH_HOME>/profiles/<profile>/cordis.patch.yml`（顶层是一个 YAML 数组）

```yaml
# ── COROS MCP ────────────────────────────────────────────────────────────────
- insert:
    - id: mcp-coros
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: coros
        transport: stdio
        command: 'C:/Program Files/nodejs/node.exe'
        args:
          - '<repo>/coros-mcp-proxy.js'
          - 'https://mcpcn.coros.com/mcp'
        toolCallTimeoutMs: 120000
```

几个必须注意的点：

- **`- insert:` 是一个数组元素**，里面才是行定义。写成 `- id: mcp-coros` 会变成"改已有行"而报找不到目标。
- **路径用正斜杠**（`C:/...`），YAML 里反斜杠是转义符。
- `toolCallTimeoutMs: 120000` —— 写课表/建计划这类操作比读数据慢，默认 60s 容易超时。
- **改完必须重启 DSH**（插件树只在启动时结算；刷新页面无效）。
- 改动前先备份：`Copy-Item cordis.patch.yml cordis.patch.yml.bak-<时间戳>`。

### 步骤 D：语法校验（别靠肉眼）

```powershell
# 用 PyYAML 直接 parse，确认顶层是 array、条目数对得上
@'
import yaml
d = yaml.safe_load(open(r"<DSH_HOME>\profiles\desktop\cordis.patch.yml", encoding="utf-8"))
print(type(d).__name__, len(d))
for e in d: print(list(e.keys()))
'@ | python -
```

期望输出：`list N`，最后一条是 `['insert']`。

> 一个坑：PowerShell 里用 `"  " + $_` 给每行加前缀打印，很容易误判"文件被整体缩进了 2 格"。
> **校验缩进要看 `Get-Content -Raw` 的原始输出。**

### 步骤 E：重启并验证

重启 DSH 后，工具会以 `mcp__coros__<tool>` 出现在模型工具列表里。最小验证：

```
调用 mcp__coros__queryUserInfo        → 应返回身高/体重/生日等资料
调用 mcp__coros__queryRecoveryStatus  → 应返回恢复百分比
```

**能返回真实数据才算通**，只看"工具出现了"不算。然后再验证写操作（原本会炸的那一半）：

```
调用 mcp__coros__createScheduledWorkout / updateScheduledWorkout
```

---

## 4. 排错对照表

| 症状 | 原因 | 处理 |
|---|---|---|
| `Pointer '/$defs/Section' does not exist`，整轮失败 | COROS schema 缺陷，被 API 严格校验 | 上代理（步骤 B）；或临时只保留读工具 |
| 工具列表里没有 `mcp__coros__*` | 行没生效 / mcp-remote 未登录 / 启动失败 | 看宿主日志；单独跑一次 `npx -y mcp-remote@0.14.3 <url>` 确认登录 |
| `spawn npx ENOENT` / `EINVAL` | Windows 下 `npx` 解析到无扩展名脚本 | 改成 `node + npx-cli.js`（本仓库写法），或设 `MCP_REMOTE_NPX_CLI` |
| 启动慢 5 秒左右 | 每次启动都要跑一遍 npm exec 解析 + OAuth 发现 + `tools/list` | 可接受；DSH 会等插件树结算后才打印就绪 URL |
| 调用超时 | `toolCallTimeoutMs` 默认 60s | 调到 `120000` |
| 换机器/换盘后失效 | 配置里写死了路径 | 同步改 `command` 与 `args[0]` |
| 授权过期 | refresh_token 失效 | 手动跑一次 `npx -y mcp-remote@0.14.3 <url>` 重新登录 |
| 端口/区域不对 | 非中国区账号 | issuer 换 `mcpeu` / `mcpus` |

**关于"整轮失败"的一个经验**：MCP 工具的 schema 由**服务端**提供，DSH 只做转发。
遇到"某个 MCP 一启用就整轮挂"，先按 `$ref` / `$defs` / `anyOf` 这类结构去查 schema，比查代码快得多。

诊断思路（本次实际用到的）：

1. 把 `tools/list` 的原始响应存成 JSON（`tools_list.json`）；
2. 统计每个工具里 `$ref` 与 `$defs` 的出现次数与位置；
3. `$ref` 指 `#/` 而 `$defs` 不在根 → 命中。

---

## 5. 回滚

```powershell
Copy-Item '<DSH_HOME>\profiles\desktop\cordis.patch.yml.bak-<时间戳>' `
          '<DSH_HOME>\profiles\desktop\cordis.patch.yml' -Force
# 重启 DSH 即回到"没有 COROS"的状态
```

只删 `coros` 那一段 `- insert:` 也可以；`dsh-mcp-client` 是宿主内置的，不用卸任何包。

---

## 6. 等 COROS 修好之后怎么简化

服务端把 `$defs` 挪到根之后，代理就没必要了，配置可以缩成：

```yaml
- insert:
    - id: mcp-coros
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: coros
        transport: stdio
        command: npx
        args: ['-y', 'mcp-remote@0.14.3', 'https://mcpcn.coros.com/mcp']
        toolCallTimeoutMs: 120000
```

判断标准很简单：**不挂代理重启一次，直接调 `mcp__coros__createScheduledWorkout` 不报 schema 错**，就说明修好了。

---

## 7. 落地的文件清单

| 文件 | 作用 |
|---|---|
| `<DSH_HOME>/profiles/<profile>/cordis.patch.yml` | MCP 行（含注释与回退方法） |
| `<repo>/coros-mcp-proxy.js` | `$defs` 提升代理（零依赖） |
| `~/.mcp-auth/mcp-remote-v1/*_tokens.json` | OAuth 登录态（30 天有效 + refresh） |
| `cordis.patch.yml.bak-*` | 回滚点 |

---

## 8. 可复用的方法论（比 COROS 本身更有价值）

1. **先分层验证，再合并。** 鉴权（mcp-remote 单跑）→ 协议（stdio 手喂 JSON-RPC）→ 集成（DSH 行）。
   一次只引入一个变量，出错时才能定位。
2. **把"服务端的锅"和"客户端的锅"分开。** 本次大部分时间花在确认到底是 DSH、mcp-remote 还是 COROS 的问题；
   最后靠 `tools_list.json` 里原始 schema 一锤定音。
3. **代理只做最小改写。** 能透传就透传，只在必须改的那一种消息上动手——这样上游升级时代理不容易坏。
4. **配置里写清"为什么"和"怎么回退"。** 注释比配置本身重要，半年后你只会记得"这里有个坑"。
5. **凡是"一处坏就全盘失败"的系统，优先怀疑 schema/协议层，而不是业务逻辑。**
