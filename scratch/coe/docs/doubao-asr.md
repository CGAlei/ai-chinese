# 豆包 Cloud ASR + Coe

这篇文档说明怎样把 Coe 接到豆包云端 ASR。

对应实现见 [internal/asr/doubao.go](../internal/asr/doubao.go)。

## 1. 适用场景

适合下面这种情况：

- 你想用云端 ASR，但不想走 OpenAI
- 你已经有豆包语音控制台的 API key
- 你接受录音结束以后，再一次性上传整段 WAV 做识别

当前这个 provider 走的是豆包录音文件极速版识别接口，不是流式 ASR。

## 2. 准备 API key

Coe 读取豆包 key 的方式有两种：

- 配在环境变量 `DOUBAO_ASR_API_KEY`
- 直接写在 `asr.api_key`

更推荐环境变量方式，因为这样不用把密钥写进配置文件。

如果你已经有 `~/.config/coe/env`，加一行：

```bash
DOUBAO_ASR_API_KEY=your-key
```

改完以后执行：

```bash
coe restart
```

## 3. 配置 Coe

编辑 `~/.config/coe/config.yaml`，把 `asr` 改成这样：

```yaml
asr:
  provider: doubao
  endpoint: https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash
  model: ""
  language: ""
  prompt: ""
  api_key: ""
  api_key_env: DOUBAO_ASR_API_KEY
```

最关键的是三项：

- `provider` 必须是 `doubao`
- `endpoint` 留空时，也会回退到官方默认接口
- `api_key_env` 留空时，也会回退到 `DOUBAO_ASR_API_KEY`

v1 里，这个 provider 会忽略下面这些字段：

- `model`
- `language`
- `prompt`
- `prompt_file`

这是因为当前接的是固定接口形态，不需要用户再选模型名。

## 4. 先单独验证 ASR

如果你想先排除 LLM 干扰，建议暂时把：

```yaml
llm:
  provider: stub
```

这样可以先确认问题是在 ASR 还是在后处理。

然后执行：

```bash
coe doctor
```

如果配置正常，`ASR provider` 这一项里应该能看到：

- `provider=doubao`
- 豆包 endpoint
- API key 的来源

## 5. 运行时行为

Coe 会把录到的音频编码成 base64 WAV，然后发到豆包接口。

如果接口返回非成功状态，错误里会带上 `doubao transcription failed` 和关键状态信息。

如果接口成功但文本为空，pipeline 会把它当成空转写处理，不会继续做后续输出。

## 6. 常见问题

### `ASR provider=doubao but no API key is available`

说明 `asr.api_key` 和 `asr.api_key_env` 都没有取到值。

先检查：

- `DOUBAO_ASR_API_KEY` 是否真的存在
- 改完 env 以后是否执行过 `coe restart`
- `config.yaml` 里有没有把 `api_key_env` 拼错

### 能请求成功，但一直没有文本

先把 `llm.provider` 设成 `stub`，确认不是 LLM 清洗阶段把文本改空。

如果还是空，再看 `coe serve --log-level debug` 的日志，确认豆包返回体里是否已经没有可用文本。

## 7. 相关文档

- [configuration.md](./configuration.md)
- [README.md](../README.md)
