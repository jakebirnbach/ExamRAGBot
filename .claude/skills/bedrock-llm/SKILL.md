---
name: bedrock-llm
description: Use when working on answer generation or anything that calls Claude on AWS Bedrock - the LLM adapters, model IDs, AWS credentials/profiles/regions, model access errors, the default Haiku 4.5 setup or moving to Haiku 5.5, the answer prompt, or running paid Bedrock tests. Covers the verified setup on this account (Haiku 4.5 via Converse; 5.5 not enabled), the shell AWS_* variable trap, how to diagnose "model does not exist / not available for this account", the two adapters, and costs. Triggers - "bedrock", "claude", "haiku", "ask command", "answer quality", "model not available", "AccessDenied", "switch to haiku 5.5", "aws profile", "LLM error".
---

# Claude on Bedrock

## Current state (2026-11-01)

- AWS account `733118130762`, region **us-east-1**, IAM user/profile **`exam-rag-bot`**
  (AmazonBedrockFullAccess; narrow it to invoke-only before deployment). Never use root.
- **The app uses Claude Haiku 4.5 via the Converse API.** That's the code default
  (`BEDROCK_API=converse`, `us.anthropic.claude-haiku-4-5-20251001-v1:0`); the user chose it.
- **Haiku 5.5 is not enabled on this account.** Every API call returns "anthropic.claude-haiku-5-5
  is not available for this account", in every US region, with both `us.` and `global.` IDs, and
  as both the IAM user and root. The Anthropic use-case form is on file. The account card had
  expired (possibly related: new model subscriptions go through Marketplace billing). The
  console playground "working" turned out to be Haiku 4.5 (check the model selector).
- To move to 5.5 later: confirm a call succeeds (diagnostics below), then set
  `BEDROCK_API=messages` and `BEDROCK_MODEL_ID=anthropic.claude-haiku-5-5`, and run the smoke test.

## Settings (`infrastructure/config.py`) and the AWS env trap

| Setting | Default | Notes |
|---|---|---|
| `BEDROCK_API` | `converse` | `converse` = boto3 Converse (Haiku 4.5); `messages` = Anthropic SDK client (Haiku 5.5) |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | A blank line in .env means "use the default" |
| `BEDROCK_AWS_PROFILE` | none | `exam-rag-bot` in .env |
| `BEDROCK_REGION` | `us-east-1` | |
| `LLM_EFFORT` | `low` | messages adapter only (Haiku 5.5 thinks adaptively; effort controls it) |
| `LLM_MAX_TOKENS` | 4096 | Covers thinking plus answer |

**The app deliberately does not read `AWS_PROFILE` / `AWS_REGION`.** The user's shell exports
`AWS_PROFILE=default` (root credentials) and `AWS_REGION=us-east-2` (from other work), and
environment variables override `.env` in pydantic-settings. Never rename these settings back.

## The two adapters (`infrastructure/llm/`)

**`bedrock_claude.py` (`BedrockClaudeLLM`, for Haiku 5.5 / current models; not the default):** `anthropic.AnthropicBedrockMantle(aws_region=, aws_profile=, timeout=, max_retries=)`
(requires the `anthropic[bedrock]` extra; signing uses boto3/botocore lazily).
`messages.create(model, max_tokens, system, messages, output_config={"effort": ...})`.
- No `temperature`: the SDK (2.x) doesn't accept it and current models return a 400 for it.
- Read text **by block type**: Haiku 5.5 thinks by default, so `thinking` blocks can come first,
  and thinking counts toward `max_tokens`.
- `stop_reason == "refusal"` → `LLMRefusalError(stop_details.category)`. Haiku 5.5 has no
  server-side fallback; health/education questions shouldn't trigger it.
- Errors are mapped most-specific first: NotFound, Auth/PermissionDenied, RateLimit,
  APIStatusError, APIConnectionError → `LLMError`.
- Use `AssistantMessageParam`/`UserMessageParam` to build messages (mypy rejects a dict with a
  variable role).
- **It can't reach older models like Haiku 4.5** (403/404); Bedrock serves those only through its
  legacy runtime.

**`bedrock_converse.py` (`BedrockConverseLLM`, default):** `boto3.Session(profile_name, region_name).client("bedrock-runtime")`,
`converse(modelId, system=[{"text"}], messages=[{"role", "content": [{"text"}]}], inferenceConfig={"maxTokens"})`.
Text is joined from `output.message.content[*].text`. A `stopReason` of `content_filtered` or
`guardrail_intervened` → refusal. A `ClientError` code is mapped to `LLMError`.

## Diagnosing access problems (free, read-only checks first)

```
aws bedrock get-foundation-model-availability --model-id anthropic.claude-haiku-5-5 --profile exam-rag-bot --region us-east-1
aws bedrock get-use-case-for-model-access --profile exam-rag-bot --region us-east-1
aws bedrock list-inference-profiles --profile exam-rag-bot --region us-east-1 --query 'inferenceProfileSummaries[].inferenceProfileId'
```

- The Anthropic SDK endpoint reports **every** access problem as `404 "model … does not exist"`,
  which is misleading. For the real reason, make one Converse call with the CLI:
  `aws bedrock-runtime converse --profile exam-rag-bot --region us-east-1 --model-id <id> --messages '[{"role":"user","content":[{"text":"Say OK."}]}]'`
  It returns e.g. `AccessDeniedException: … is not available for this account`. Denied calls aren't billed.
- `agreementAvailability: NOT_AVAILABLE` showed for every Claude model, including the working
  Haiku 4.5, so it isn't a reliable signal on its own.
- Haiku 5.5 supports only inference-profile invocation (`us.` / `global.` prefixes on
  `bedrock-runtime`); the Anthropic SDK client uses `anthropic.claude-haiku-5-5`.

## Testing

- Unit tests use stand-in clients (`tests/unit/infrastructure/test_bedrock_*.py`); there are no
  AWS calls in unit tests.
- Paid smoke test, which uses whatever `BEDROCK_API` selects:
  `RUN_BEDROCK_TESTS=1 uv run pytest -q tests/integration/test_bedrock_claude.py`.
  **Ask the user before making paid calls.**
- End to end: `uv run study-assistant ask "What are the four processes of motivational interviewing?"`.
  Good reference questions: that one; an ambivalent-client scenario (should identify Contemplation);
  an off-topic one such as "capital of Australia" (should say "not covered", with no citations).

## Cost and latency

Per question, the prompt is about 3k tokens of excerpts plus about 300 output tokens.
Haiku 5.5 is $0.10/$0.50 per million tokens (first-party prices; Bedrock pricing may differ);
Haiku 4.5 is $1/$5, which is still well under a cent per question. A warm `ask` takes about
9–12 s (embedding, Pinecone, reranking about 4 s, then the LLM); a cold start adds about 10–15 s
for model loads.
