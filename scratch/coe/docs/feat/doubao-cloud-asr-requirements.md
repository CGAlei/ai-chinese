# Coe 接入豆包 Cloud ASR 需求

## 0. 文档角色

这份文档只定义一件事：

- `Coe` 如何新增一个豆包云端语音识别 provider，用来替代或补充现有 `openai` / 本地 ASR provider

这份文档先回答：

- 现有架构下接哪一个豆包 ASR 接口最合适
- v1 要支持什么，不支持什么
- 配置、请求、响应和错误处理应该怎么收敛

这里先不写实现细节代码，但会尽量把接口约束说清楚，避免后面边做边改方向。

## 1. 背景

当前 `Coe` 的 ASR provider 接口已经比较稳定：

- 录音先在本地完成
- provider 拿到的是一段完整音频
- provider 返回一次最终转写结果

现有 provider 里：

- `openai` 是一次 HTTP 上传音频并拿到文本
- `sensevoice` 是本地 HTTP 服务
- `qwen3-asr-vllm` 是一次 HTTP chat-completions 请求
- `whispercpp` 是本地 CLI

也就是说，当前 `Coe` 的 ASR 主链路是：

- **完整音频 -> 单次请求 -> 最终文本**

这对接云端文件识别接口很自然，但并不适合直接塞入 WebSocket 流式协议。

## 2. 调研结论

### 2.1 豆包官方可选 ASR 形态

豆包语音官方文档里，和当前需求最相关的语音识别大模型接口主要有三类：

- 大模型流式语音识别 API
- 大模型录音文件识别标准版 API
- 大模型录音文件极速版识别 API

从 `Coe` 当前架构出发，真正契合的是“录音文件极速版识别 API”，原因很直接：

- 它是单次 HTTP 请求
- 一次请求直接返回最终结果
- 不需要 submit/query 两段式轮询
- 也不需要为了 provider 单独引入流式双向状态机

因此 v1 的接口选择应明确为：

- **豆包大模型录音文件极速版识别 API**

不选其他两类接口的原因：

- 不选流式 API：当前 `Coe` 不是边录边传、边传边出字的架构
- 不选标准版 API：它是 submit/query 两段式，复杂度更高，但对 `Coe` 当前短语音转写场景没有明显收益

### 2.2 官方接口关键信息

根据豆包语音官方文档，极速版接口的关键约束如下：

- 接口地址：
  - `POST https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash`
- 调用形态：
  - 一次请求直接返回识别结果
- 音频限制：
  - 时长不超过 `2h`
  - 大小不超过 `100MB`
  - 支持 `WAV / MP3 / OGG OPUS`
- 资源 ID：
  - `volc.bigasr.auc_turbo`
- 请求体：
  - `audio.url` 或 `audio.data` 二选一
  - `request.model_name` 示例值为 `bigmodel`
- 成功结果：
  - 响应体里有 `result.text`
  - 也可能包含 `utterances` / `words`
- 错误信号：
  - 除 HTTP 状态外，响应头里还有 `X-Api-Status-Code`、`X-Api-Message`、`X-Tt-Logid`

这些约束和 `Coe` 当前 provider 接口是相容的。

## 3. v1 范围

### 3.1 v1 要做什么

v1 只做最小可用版本：

- 新增一个豆包云端 ASR provider
- 通过官方“录音文件极速版识别 API”上传完整音频
- 读取返回体里的最终文本并接到现有 pipeline
- 复用现有 `asr.api_key` / `asr.api_key_env` 配置方式
- 复用现有 `audio.EncodeWAV()`，直接上传 base64 WAV

### 3.2 v1 不做什么

v1 明确不做：

- 不接豆包流式 ASR
- 不接标准版 submit/query 两段式 API
- 不新增浏览器端、WebSocket 端或额外后台 worker
- 不做 URL 音频转写模式，`Coe` 只传本地录到的音频
- 不做热词表、自学习平台、speaker info、情绪识别等额外能力
- 不把豆包 provider 做成“OpenAI 兼容端点”假装复用 `openai` provider

## 4. provider 命名与配置

### 4.1 provider 名称

建议把新 provider 名称定成：

- `doubao`

原因很简单：

- 这次需求只接一种豆包云端 ASR
- `Coe` 现有 provider 名称也大多是产品级名字，不是接口级名字
- 如果以后真要接别的豆包 ASR 形态，再单独拆名字也不晚

### 4.2 配置草案

建议的 v1 最小配置形态：

```yaml
asr:
  provider: doubao
  api_key_env: DOUBAO_ASR_API_KEY
```

说明：

- `provider`
  - 必须是 `doubao`
- `api_key` / `api_key_env`
  - 复用现有云端 provider 的配置模式

如果确实需要覆盖接口地址，允许额外配置：

```yaml
asr:
  provider: doubao
  endpoint: https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash
  api_key_env: DOUBAO_ASR_API_KEY
```

但 v1 不把 `model` 暴露成用户配置项。`request.model_name` 由代码固定写死为官方最小可用值。

### 4.3 v1 鉴权取舍

官方文档同时给了两套头部：

- 旧版控制台：
  - `X-Api-App-Key`
  - `X-Api-Access-Key`
- 新版控制台：
  - `X-Api-Key`

从 `Coe` 当前配置结构出发，v1 最合理的取舍是：

- **只支持新版控制台的 `X-Api-Key`**

原因：

- 当前 `ASRConfig` 只有一组 `api_key` / `api_key_env`
- 如果同时兼容旧版控制台，就要新增 `app_id` / `access_key` 之类字段
- 这会把新需求从“加一个 provider”扩大成“重塑整个 ASR 鉴权配置模型”

因此 v1 结论应明确：

- `doubao` 只支持新版控制台 `X-Api-Key`
- 旧版控制台暂不支持

## 5. 请求映射

### 5.1 音频上传方式

官方接口支持：

- `audio.url`
- `audio.data`

对 `Coe` 来说，v1 应只用：

- `audio.data`

原因：

- `Coe` 当前拿到的是本地录音结果，不是公网 URL
- 直接把内存中的 WAV 做 base64，最简单，也最贴合现有 provider 结构

### 5.2 请求头

v1 请求头应固定包含：

- `X-Api-Key: <api key>`
- `X-Api-Resource-Id: volc.bigasr.auc_turbo`
- `X-Api-Request-Id: <uuid>`
- `X-Api-Sequence: -1`

这里不额外开放配置：

- `X-Api-Resource-Id`
  - 固定写死 `volc.bigasr.auc_turbo`
- `X-Api-Request-Id`
  - 每次请求生成新的 UUID
  - 只用于排查和日志追踪

### 5.3 请求体

v1 建议发送的最小请求体：

```json
{
  "user": {
    "uid": "coe"
  },
  "audio": {
    "data": "<base64 wav>"
  },
  "request": {
    "model_name": "bigmodel"
  }
}
```

其中：

- `audio.data`
  - 来自 `audio.EncodeWAV()` 的结果再做 base64
- `request.model_name`
  - 固定 `bigmodel`

### 5.4 `user.uid` 的取舍

`user.uid` 在 v1 不承载鉴权语义。

这里直接定死一条约束：

- 不复用 `api_key`
- 先用固定非敏感字符串，例如 `coe`

原因：

- `uid` 从字段语义看更像业务侧标识，不是密钥
- 把 `api_key` 塞进去没有必要，还可能增加日志泄露风险

如果后续真实联调证明豆包接口对 `uid` 有更强约束，再单独调整。但在需求层面，不应把 `uid` 设计成密钥字段。

## 6. 响应映射

### 6.1 成功响应

成功时，v1 应优先读取：

- `result.text`

如果 `result.text` 非空：

- 直接作为 ASR 文本返回给 pipeline

### 6.2 空文本处理

如果 `result.text` 为空：

- v1 直接返回空文本
- 可以附带 warning，方便日志定位

`utterances` / `words` 暂时不进入 v1 需求范围。  
原因很简单：当前没有足够事实证明 `result.text` 不够用，不必先为将来增加解析分支。

### 6.3 头部状态与日志

除了 HTTP status，v1 还应记录并利用：

- `X-Api-Status-Code`
- `X-Api-Message`
- `X-Tt-Logid`

建议做法：

- 只要 `X-Tt-Logid` 存在，就写进 warning / error 文本或结构化日志
- 出现服务端错误时，把 `X-Tt-Logid` 打出来，方便用户去火山引擎侧排查

## 7. 错误处理

### 7.1 直接失败

以下情况应直接报错：

- 缺少 API key
- HTTP 请求失败
- HTTP 返回非 2xx
- 服务端返回明确失败状态

### 7.2 先不细分 provider 内部状态码

v1 不在需求文档里枚举豆包的内部错误码表。

原因：

- 这些码值属于 provider 细节
- 先把“失败时能看出 provider、HTTP 状态、服务端状态和 `X-Tt-Logid`”做好，更重要
- 真正需要单独分流哪些状态，再等联调后补

## 8. 与现有配置字段的关系

### 8.1 可以直接复用的字段

这些字段可以直接复用：

- `asr.provider`
- `asr.endpoint`
- `asr.api_key`
- `asr.api_key_env`

### 8.2 v1 先不支持的字段

这些字段在 `doubao` v1 里不建议生效：

- `asr.model`
- `asr.language`
- `asr.prompt`
- `asr.prompt_file`

原因：

- `model_name` 在 v1 里固定即可，没有证据表明用户现在需要改它
- 官方极速版接口文档没有给出和 OpenAI transcription 同等语义的 `language` / `prompt` 文本引导参数
- 如果把 `prompt` 硬映射到别的字段，会让用户以为行为与 `openai` provider 一致，但实际上不是

因此 v1 建议：

- 这些字段对 `doubao` 暂时忽略
- 如果配置了它们，可以在日志里给一条低级别 warning

## 9. 实现建议

### 9.1 代码落点

建议的实现位置：

- `internal/asr/client.go`
  - 新增 provider 常量与分支
- `internal/asr/doubao.go`
  - 单独实现豆包极速版客户端
- `internal/asr/doubao_test.go`
  - 覆盖请求头、请求体、成功/错误响应解析

### 9.2 实现方式

建议实现方式与现有 `openai` provider 对齐：

- 复用 `audio.EncodeWAV()`
- 用 `net/http` 直接发 JSON 请求
- 默认 `http.Client` 超时单独设置
- 不引入第三方 SDK

这样做的好处：

- transport 简单
- 测试容易写
- provider 行为边界清楚

### 9.3 超时建议

虽然官方极速版是单次同步返回，但它毕竟是云端接口。  
建议 v1 里给一个明确的 HTTP 超时，例如：

- `60s`

这样比较接近当前 `openai` / `qwen3-asr-vllm` provider 的行为。

## 10. 验收标准

满足以下条件则认为这个需求完成：

1. `asr.provider: doubao` 时，`Coe` 能把本地录音以 base64 WAV 发到豆包极速版接口
2. `result.text` 能被正确解析并进入现有 pipeline
3. 缺少 API key 时，错误信息清楚
4. 服务端返回失败时，错误信息中能看出豆包 provider 和关键状态
5. `X-Tt-Logid` 能在失败日志里保留下来
6. 不需要新增新的全局配置文件格式
7. 不影响现有 `openai` / `sensevoice` / `whispercpp` / `qwen3-asr-vllm`

## 11. 当前结论

从调研结果看，这个需求是可行的，而且适合当前 `Coe` 架构。

更具体地说：

- **豆包“录音文件极速版”接口形态和 `Coe` 现有 ASR provider 契合**
- **v1 可以只支持新版控制台 `X-Api-Key`，不需要重构整个配置模型**
- **实现上更像新增一个普通 HTTP provider，不需要改 pipeline 主结构**
- **v1 应尽量少暴露配置，先把最小可用路径打通**

## 12. 调研依据

官方文档：

- 豆包语音 大模型录音文件极速版识别 API
  - https://www.volcengine.com/docs/6561/1631584
- 豆包语音 大模型录音文件识别标准版 API
  - https://www.volcengine.com/docs/6561/1354868
- 豆包语音 控制台使用 FAQ
  - https://www.volcengine.com/docs/6561/196768

仓库内相关代码：

- [internal/asr/client.go](../../internal/asr/client.go)
- [internal/asr/openai.go](../../internal/asr/openai.go)
- [internal/asr/qwen3_vllm.go](../../internal/asr/qwen3_vllm.go)
- [internal/config/config.go](../../internal/config/config.go)
