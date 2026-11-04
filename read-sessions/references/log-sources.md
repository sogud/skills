# 各 Agent 会话日志位置与格式

2026-08-12 在本机实测（macOS）。

## 位置

| Agent | 位置 | 备注 |
| --- | --- | --- |
| Codex | `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl` | 按日期分目录；文件名时间戳是创建时间，排序用 mtime |
| Codex SQLite | `~/.codex/state_<版本>.sqlite`、`~/.codex/thread_history_<版本>.sqlite` | 优先主目录；仅主目录对应库缺失时回退 `~/.codex/sqlite/`。`CODEX_HOME` 可指定根目录 |
| Claude Code | `~/.claude/projects/<encoded-cwd>/*.jsonl` | encoded-cwd = 绝对路径把 `/` 换成 `-` |
| Qoder CLI | `~/.qoder/projects/<encoded-cwd>/*.jsonl` | 同 Claude 的目录编码规则 |
| Pi | `~/.pi/agent/sessions/<encoded-cwd>/*.jsonl` | 使用会话头的 cwd 核对目录，不依赖文件名；2026-11-03 实测 |

## Codex SQLite 会话来源

- Codex 不只保存 JSONL。`state_*` 的 `threads` 是登记表，`thread_spawn_edges` 和显式 subagent 来源用于分类；`thread_history_*` 的 `thread_items` 保存 UI 历史项。
- 目录发现合并登记 ID、历史-only ID、JSONL 会话头和登记的文件位置，按 ID 去重。原始文件必须用自身会话头确认归属，不能因为某个登记项指向该路径就把文件当作该会话。
- `list --agent codex --count` 只输出元数据数量，不选择 `title`、`first_user_message` 或 `item_json`。Codex 普通列表也不读取正文；其它 Agent 的 `--metadata-only` 跳过对话预览。
- `sessions` 是已发现的本机 ID/文件条目，`registered` 是登记项，`main/subagent/unknown` 是来源分类，`with_sqlite_history`、`with_jsonl` 和 `metadata_only` 表示存储覆盖。`history_only` 是有历史项但未登记的 ID。`dialogue_indexed` 仅代表同时有用户和助手项类型，`main_dialogue_indexed` 进一步限非子代理登记项，不等于人工验收过正文。
- `codex:<thread-id>` 明确读取 SQLite；裸 ID 可唯一匹配时优先已核实的 JSONL。没有历史项或可用文件的登记项不能冒充可导出对话。App 里的云端/仅目录索引不作为本机正文来源。
- SQLite 始终以只读连接与 `query_only` 查询，不迁移、修复或修改真实数据库。正文只在用户显式选择会话读取、导出或取工具详情时查询；功能测试使用合成数据库。

## 格式

以下过滤规则用于渐进式读取、分析 JSONL 的对话事件和简版 Markdown；原始 JSONL 日志保持不变。

Codex（event_msg 包装）：

```json
{"type":"event_msg","payload":{"type":"user_message","message":"..."}}
{"type":"event_msg","payload":{"type":"agent_message","message":"..."}}
```

Codex 的另一种记录（2026-09-11 本机日志核对）：

```json
{"type":"session_meta","payload":{"cwd":"/path/to/workspace"}}
{"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"..."}]}}
{"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"..."}]}}
```

`list --cwd` 对 Codex 使用 `session_meta.payload.cwd`，对 Pi 使用 `session.cwd`，对 Claude/Qoder 使用项目目录编码，均匹配指定目录本身，不包含子仓或 worktree。Codex/Pi 缺少 cwd 的日志不会进入带 `--cwd` 的结果。

Pi（2026-11-03 按实际日志字段核对）：

```json
{"type":"session","version":3,"id":"session-id","cwd":"/path/to/project"}
{"type":"message","message":{"role":"user","content":[{"type":"text","text":"..."}]}}
{"type":"message","message":{"role":"assistant","content":[{"type":"text","text":"..."},{"type":"toolCall","id":"call-id","name":"read","arguments":{}}]}}
{"type":"message","message":{"role":"toolResult","toolCallId":"call-id","toolName":"read","content":[{"type":"text","text":"..."}]}}
{"type":"compaction","summary":"...","firstKeptEntryId":"entry-id"}
```

Claude / Qoder（同构）：

```json
{"type":"user","message":{"role":"user","content":"..." 或 [{"type":"text","text":"..."}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"..."}, {"type":"tool_use",...}]}}
```

解析要点：

- Claude/Qoder 的 `content` 是数组时只取 `type=text` 块；`tool_use` / `tool_result` 块跳过。
- Codex 的 `response_item` 只读 user/assistant 的 `message` 文本，不读 developer、reasoning、tool call 或 tool output。
- `isSidechain: true` 是子代理（如 Task 工具）消息，跳过。
- Claude/Qoder 的 `isMeta: true` 是技能或上下文注入，默认跳过且不切换用户消息区间。`[Request interrupted by user]` 和旧 Claude 中 `<analysis>…</analysis><summary>…</summary>` 压缩文本同样不计为纯对话；需要分析注入/压缩时定向读取原记录。
- 跳过以下用户消息前缀：`<local-command-caveat>`、`<command-message>`、`<system-reminder>`、`Caveat: The messages below were generated`（本地命令回显和系统注入，不是真实对话）。
- 同一需求可能有多个会话（重跑、续聊），Codex 文件名时间晚的不一定是最新进展，按 mtime 排序。
- compact 通常改变模型本轮使用的上下文，不等于原始日志已删除。先检查源文件；Pi 实测会追加 `compaction` 条目并保留此前原始消息，仍可读取与导出。只有日志本身已被裁切、覆盖、清理或没有保存原文时，才无法恢复原话。`openspec`、Git 和平台状态用于核实事实，不能替代或补写原始对话。
- 工作区 AGENTS、environment、skill、推荐插件、system-reminder 和 task-notification 不作为任务正文。按文本块移除已识别的注入内容，保留同一消息中的真实请求。
- 同一段对话中相邻且正文相同的 Codex event_msg/response_item 副本只保留第一条；不合并同一格式下重复发送的用户文本。跨会话重叠仍需阅读者核对。
- 脚本没有自动脱敏。不要把原始记录或完整提取结果提交到仓库、上传或作为 Harness 知识保存。

## 导出分析视图

- `export <session>` 默认生成 `<session-stem>.analysis.jsonl`。`--format md` 生成 `<session-stem>.simple.md`，只供阅读对话；不再生成含全部工具正文和原始记录的 Markdown。
- 两种格式共用对话过滤和相邻 Codex 跨格式去重。对话正文完整保留，不摘要、不改写、不受预览字符上限影响；`timestamp` 优先取原始记录顶层值，缺失时取 message/payload 的值，不转换时间单位，未知为 null。
- 分析文件每行一个 JSON 对象，按原始行号或 SQLite ordinal 排列，同一位置先放对话，再按内容块顺序放工具索引。JSONL 的非对象值和不完整行只记数量，不把原文混入分析视图；原始存储始终保留。SQLite 不支持的 UI 项不会被改造成用户/助手文字。

| type | 字段与含义 |
| --- | --- |
| `session` | 来源 `source`、存储种类 `source_kind`、指纹范围 `fingerprint_scope`、`schema_version`、读取字节数、SHA-256、来源条目数、对话数、调用数、孤立结果数及解析失败数量。SQLite 另记 `source_database`。 |
| `message` | `id=m<位置>`、`line`、`turn`、`role`、`timestamp` 和完整 `text`；SQLite 另记 `source_ref`。 |
| `tool_call` | 选择器 `id=c<位置>.<块号>`、`call_id`、`name`、`timestamp`、`message_id`、`line/block`、输入输出文字字符数、`has_result` 与 `result_refs`；不包含参数或结果正文。SQLite 可带已保存的 `status` 和 `source_ref`。 |
| `tool_result` | 仅用于没有匹配调用的结果，标记 `orphan=true`，保留调用 ID、原始行/块号、时间、文字字符数和所在用户消息；不包含结果正文。 |

- 用分析头的 `source`、调用的 `message_id` 和 `id` 运行 `tools <source> --message <message_id> --call <id> --part input|output`，按需取得对应原文。`result_refs` 保留各段结果的行号、块号、字符数及原时间；结果晚于下一条用户消息时仍按调用 ID 配对。
- `has_result` 只表示有结果记录，不等于成功。字符数沿用现有 `tools` 的文本表示计数，不是原始字节数或 Token 数。没有上游用户消息时 `message_id` 为 null，按原始行核对，不伪造可用的轮次。缺少结果时索引的 `has_result=false`，结果位置为空。
- 系统提示、上下文注入、分析内容、sidechain、模型用量、图片与工具正文不进入默认分析视图。原始 JSONL/数据库是长期数据来源，分析文件不是无损备份；JSONL 归档直接复制原文件，SQLite 使用一致性备份，不把重新序列化的分析视图当作数据库原件。
- 读取使用严格 UTF-8，非法编码会报错，不用替换字符冒充原文。JSONL 的 `fingerprint_scope=source_prefix`，来源指纹覆盖读取的文件字节前缀；活动会话追加后原前缀仍可核对。SQLite 的 `fingerprint_scope=stored_thread_items`，指纹覆盖同一只读事务读取的保存项序列化内容，不是 `.sqlite` 文件字节。
- SQLite 的位置为 `rollout_ordinal+1`，不是物理行；`source_ref` 标记数据库路径、thread ID、`item_id`、原 ordinal 和项类型。用户/助手项映射为文字，工具项映射为保存字段的输入和结果/状态快照。工具实例 `call_id` 使用 `sqlite:<item_id>`，不冒充 provider 原始调用 ID；独立输出项保留为孤立结果。
- SQLite 结果/状态字段存在时 `has_result` 可为 true，包括未完成状态；检查实际保存的 `status`，不能据此声称执行成功。工具详情仅是 UI 历史字段的投影，不保证保存了原始参数、完整输出、初始系统提示或其它未入库内容。SQLite `timestamp` 取 `created_at_ms`，同一保存项中的结果引用时间不是独立的完成时间。
- 现有 `tools` 不自动校验导出头指纹。SQLite 投影可在导出后更新，原日志重写或投影重建后应重新取索引；如需核对过去状态，使用当时的原始日志或一致性备份，不能用今天的字段补写过去。
- 默认输出到当前用户 `~/Downloads`，支持 `--output-dir` 或 `--out`。目录导出重名时自动编号；显式文件已存在则报错。文件仅用户可读写，不覆盖源日志、硬链接、软链接或已有导出。终端只打印路径与计数。
- 对话中自行包含的敏感信息仍会保留，分析文件不自动脱敏，不自动上传、提交或作为 Harness 知识保存。

## 按需读取工具

Codex/Claude/Qoder 字段于 2026-09-11 核对，Pi 字段于 2026-11-03 按实际日志核对：

| Agent | 调用 | 结果 | 配对字段 |
| --- | --- | --- | --- |
| Codex function | `response_item.payload.type=function_call`，`name`、`arguments` | `function_call_output`，`output` | `call_id` |
| Codex custom | `custom_tool_call`，`name`、`input` | `custom_tool_call_output`，`output`（字符串或内容块数组） | `call_id` |
| Claude/Qoder | `message.content[]` 中 `tool_use`，`name`、`input` | `tool_result`，`content` | 调用 `id` 对结果 `tool_use_id` |
| Pi | `message.content[]` 中 `toolCall`，`name`、`arguments` | `message.role=toolResult`，`content` | 调用 `id` 对结果 `toolCallId` |

`tail` 不收集或输出工具正文。`tools --message m123` 按消息所在的用户消息区间列调用目录，结果按调用 ID 配对，允许结果晚于下一条用户消息。`--call c140.2` 再取原日志第 140 行、第 2 个内容块的调用；Codex 单独调用记录的块号为 0。

`result-recorded` 只表示存在结果记录；`result-missing` 不能证明未执行。未知原生工具事件、嵌套在工具输出中的子任务以及二进制/图片内容不自动展开；必要时只查看对应原始记录。会话中的调用 ID 应唯一；拼接不同会话不能用同一文件冒充一个会话。

消息编号和分页游标取自 JSONL 原行号或 SQLite `rollout_ordinal+1`，不是本次输出顺序号。追加记录不会改变旧选择器；原日志重写、合并或数据库投影重建后需重新取目录。
