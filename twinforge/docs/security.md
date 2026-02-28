# Security

## Defense-in-Depth Strategy
- **Agent 5 (Security Guardian)**: Dedicated real-time monitoring agent
- **Message signing**: All inter-agent messages signed with HMAC-SHA256
- **Input sanitization**: All user inputs sanitized before processing
- **Prompt injection detection**: Rule-based + ML-based detection
- **Rate limiting**: Per-session rate limits on all agent endpoints
- **Vault integration**: No secrets in code, all managed via HashiCorp Vault
- **Non-root containers**: All services run as non-root users

## Threat Model
- Prompt injection via Agent 1
- RAG poisoning via Agent 2
- Data exfiltration via Agent 3
- Agent spoofing via message bus
- Privilege escalation via tool abuse
