# Provider 能力矩阵（模板）

> 目标：把“事实”与“兼容差异”写清楚，避免在 Phase 3+ 迁移时靠猜。  
> 填写原则：优先填写本项目实际在用/计划接入的 provider，其余可后补。

## 字段说明

- `base_url`：OpenAI-compatible 根路径（一般以 `/v1` 结尾）
- `auth`：鉴权方式（通常 `Authorization: Bearer <key>`；部分是自定义 header）
- `chat.completions`：是否支持 `/v1/chat/completions`
- `responses`：是否支持 `/v1/responses`（很多兼容提供商可能不支持）
- `stream`：是否支持 SSE 流式（以及首包超时语义是否稳定）
- `tool calling`：是否支持 `tools` / `tool_calls`（含多工具、多轮工具链路）
- `embeddings`：是否支持 `/v1/embeddings`
- `vision`：是否支持多模态输入（image_url/base64 blocks 等）

## 矩阵

| Provider | base_url | auth | chat.completions | responses | stream | tool calling | embeddings | vision | 备注 |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| OpenAI | `https://api.openai.com/v1` | Bearer | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 官方基准 |
| Azure OpenAI | `https://{resource}.openai.azure.com` | api-key | ✅ | ✅* | ✅ | ✅ | ✅ | ✅ | *以 SDK/版本为准 |
| OpenAI-compatible（通用） | `https://<provider>/v1` | Bearer | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 以事实表为准，避免“假兼容” |

> 建议：为每个 provider 额外补充一段“已验证样例”（curl 或最小 Python 片段），并记录：超时/重试/限流/错误码差异。

