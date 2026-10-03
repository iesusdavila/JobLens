# Job Fit Agent

Decide whether a job posting is worth applying to, then get a CV rewritten for that posting without inventing anything.

- **Fit analysis per job:** overall score, per-requirement verdicts (met / partial / missing, must-have or nice-to-have), seniority match, red flags, strengths, gaps, and a recommendation (`apply`, `apply_after_tailoring`, `skip`) with reasons.
- **Tailored CV per job:** reorders, rewords and condenses real evidence so ATS filters and recruiters find it. Download it as DOCX, PDF or Markdown, with a diff-style change log that gives the reason for each change.
- **Ranking:** when you analyze several jobs, a comparison table shows which to prioritize.
- **Chat assistant:** ask about the company, similar roles, how to close a skill gap, interview preparation, salary talking points or a cover letter grounded in your real profile.

## Architecture

```
Streamlit (frontend/)  --HTTP-->  FastAPI (backend/app)
                                     |
             +-----------------------+-------------------------+
             |                       |                         |
     JobIngestionService     AnalysisService            ApplicationChatService
     (httpx + bs4, robots)   (bounded concurrency,      (LangChain + Claude, 
     DocumentParserService    one agent per job)         DuckDuckGo tool, memory)
     (pypdf, python-docx)            |
                              AnalysisAgent (LangGraph, ReAct)
                              agent node <-> ToolNode, nudge, force_finalize
                                     |
        +-----------+-----------+----+-------------+---------------+----------------+
        |           |           |                  |               |                |
  extract_job   parse_candidate  run_fit_       draft_tailored_  run_cv_        finalize_
  requirements  profile          validation     cv               validation     outputs
  (LLM)         (LLM)            (Jev 1-5 +     (LLM + fact      (Jev 5-7)      (DOCX/PDF/MD)
                                 aggregator)    guard)
```

Main pieces:

| Layer | Location | Responsibility |
| - | - | - |
| Settings | `backend/app/config/settings.py` | `pydantic-settings`. Fails fast when a key is missing. Weights and thresholds are configurable. |
| Clients | `backend/app/clients/` | `JevClient` wraps `typesafe_sdk` (no other module imports the SDK). `LlmClient` wraps the chat model built by `ChatModelFactory`: Claude on Amazon Bedrock (default) or Groq. It retries when the output does not match the schema. |
| Validators | `backend/app/validators/` | One class per Jev validator, plus `FitScoreAggregator`. |
| Agents | `backend/app/agents/analysis/`, `backend/app/agents/chat/` | LangGraph reactive analysis agent and the LangChain chat agent. Prompts live in `prompts.py`. |
| Services | `backend/app/services/` | Ingestion, parsing, extraction, tailoring, evaluation, export, sessions, chat. |
| Repositories | `backend/app/repositories/` | `SessionRepository` with in-memory and JSON-file implementations. |
| API | `backend/app/api/` | Versioned routes under `/api/v1`, schemas, error handlers, size limit. |

### Why Jev validates and the LLM generates

Generating text and judging text are different jobs:

- **The LLM (Claude on Amazon Bedrock by default)** writes: it extracts requirements, structures the CV, rewrites the CV and answers chat messages.
- **Jev (System One model by TypeSafe)** judges: every decision the app relies on is an atomic, typed Jev question. Requirement met? Claim supported by the sources? Seniority below, matching or above? Jev returns calibrated probabilities and confidence instead of free text, so code can branch on them.
- **Code combines:** `FitScoreAggregator` computes the score and the recommendation with explicit weights. The LLM never produces the verdict. Weights and thresholds change through env vars, not through prompt edits.

Each Jev question asks one thing, such as "Does `candidate_evidence` show that the candidate satisfies `requirement`?". The app never asks Jev to "rate this candidate". The questions in one call are evaluated in parallel against the same state.

### Jev validators

| Class | Primitive | What it decides |
| - | - | - |
| `RequirementMatchValidator` | Noul per requirement | Met probability. Configurable thresholds map it to met / partial / missing. Long evidence is chunked and the best chunk wins. |
| `FitDimensionValidator` | Score x4 | Technical, domain, tools/stack and soft-skills fit, each on a 5-level rubric. |
| `SeniorityValidator` | Choice + Noul | Below / matches / above, and whether the candidate has the required years. |
| `RedFlagValidator` | Noul per risk | Job side: vague responsibilities, unrealistic stack, scam signals, and location/modality/salary conflicts when preferences are given. Candidate side: unexplained gaps, missing must-haves. |
| `AtsAlignmentValidator` | Noul per key term + Score x2 | Keyword coverage, terminology mirroring and prominence of priorities. It runs on both the original and the tailored CV. |
| `CvFaithfulnessValidator` | Noul per claim | Is each bullet, skill and summary sentence supported by the source documents? |
| `CvQualityValidator` | Noul + Score + code | Relevance ordering, no filler and clarity (Jev). Word count and bullets per role (code). |

### Analysis agent loop

The agent is a LangGraph `StateGraph` with an agent node (the chat model with bound tools), a `ToolNode`, a nudge node and a force-finalize node. It is not a fixed chain. The LLM reads the `STATUS:` line of each tool result and picks the next tool. Tools check their own prerequisites and say which tool to call first.

- `run_cv_validation` returns `NEEDS_REVISION` together with the exact failing items: unsupported claims, ATS terms that did not improve, quality issues. `draft_tailored_cv` feeds those items into the next draft.
- `finalize_outputs` is refused until `CvFaithfulnessValidator` passes and ATS alignment improves over the original. It becomes available earlier only when `MAX_AGENT_ITERATIONS` drafts were made or a tool failed.
- When the iteration cap is hit, the best draft is returned. Claims that were still unsupported are removed, and a warning lists the unresolved issues.
- Hard limits: a step budget (`MAX_AGENT_ITERATIONS * MAX_AGENT_STEPS_PER_ITERATION + 8`), nudges when the model stops calling tools, and a budget for tool errors. Every exit path produces a result with an actionable error or warning.
- `CvFactGuard` restores employers, titles, dates, education and certifications from the parsed profile. It also drops entries that do not exist in the source documents, before Jev sees the draft.

## Setup

Requirements: Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

- `TYPESAFE_API_KEY`: the Jev key. Create it at <https://console.typesafe.ai/>.
- `LLM_PROVIDER`: `bedrock` (default) or `groq`.
- `AWS_BEARER_TOKEN_BEDROCK`: your Amazon Bedrock API key. Create it in the AWS console under Amazon Bedrock, then API keys. Short-term keys expire after 12 hours at most; your AWS administrator may block long-term keys.
- `BEDROCK_REGION`: AWS region of the endpoint, for example `us-east-1` or `eu-west-1`.
- `BEDROCK_MODEL_ID`: the model, with the `anthropic.` prefix. Versioned ids such as `anthropic.claude-sonnet-4-5-20250929-v1:0` also work (served through Converse). Defaults to `anthropic.claude-opus-5-5`. Other options: `anthropic.claude-sonnet-5-5`, `anthropic.claude-fable-5-1`, `anthropic.claude-opus-4-8`, `anthropic.claude-sonnet-5` or `anthropic.claude-haiku-4-5`. Fable 5.1, Opus 4.8, Sonnet 5 and Haiku 4.5 are open to every Bedrock account; for Opus 5.5 and Sonnet 5.5, check access under Model access in the Bedrock console.
- `GROQ_API_KEY` / `GROQ_MODEL`: only when `LLM_PROVIDER=groq`. Create the key at <https://console.groq.com/keys>. The model defaults to `openai/gpt-oss-120b`.

Variables exported in your shell (for example in `~/.bashrc`) take precedence over `.env`.

## Run

Backend (from the project root):

```bash
uvicorn app.main:create_app --factory --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

Interactive API docs: <http://localhost:8000/docs>

Frontend (another terminal, from the project root):

```bash
streamlit run frontend/app.py
```

The UI opens at <http://localhost:8501>. It reads `BACKEND_URL` from `.env`.

Tests (Jev and the LLM are mocked, no keys needed):

```bash
pytest
```

## API

All routes live under `/api/v1`.

| Method | Path | Purpose |
| - | - | - |
| GET | `/health` | Liveness and active models. |
| POST | `/sessions` | Create a session (optional preferences). |
| GET / DELETE | `/sessions/{id}` | Read or delete a session. Deleting removes its documents. |
| PUT | `/sessions/{id}/preferences` | Locations, modality, minimum salary, notes. |
| POST | `/sessions/{id}/documents` | Multipart: `cv_file` / `cv_text`, `extra_file` / `extra_text`. Accepts PDF, DOCX, TXT and MD. |
| POST | `/sessions/{id}/jobs` | `{"jobs": [{"url": ...} or {"text": ..., "label": ...}]}`. Returns the ingestion status per job. |
| PUT | `/sessions/{id}/jobs/{job_id}/text` | Paste the description of a job whose URL could not be read. |
| DELETE | `/sessions/{id}/jobs/{job_id}` | Remove a job. |
| POST | `/sessions/{id}/analyze?background=true` | Start the agent for every readable job. Use `background=false` to wait for the result. |
| GET | `/sessions/{id}/status` | Progress and per-job status, for polling. |
| GET | `/sessions/{id}/results` | Per-job results and ranking. |
| GET | `/sessions/{id}/jobs/{job_id}/cv?format=docx\|pdf\|md` | Download the tailored CV. |
| POST | `/sessions/{id}/chat` | `{"message", "job_id"?, "stream"?}`. With `stream=true` the reply arrives as a plain-text stream. |

Every error has the shape `{"error": {"code", "message", "details"}}`.

## Configuration

The variables in `.env.example` are the main ones. Every field of `Settings` can be overridden through an env var with the same name in upper case. Nested values use `__`:

| Variable | Default | Meaning |
| - | - | - |
| `MAX_AGENT_ITERATIONS` | 6 | Maximum number of tailoring drafts per job. |
| `LLM_MAX_TOKENS` | 16000 | Output cap per LLM call (thinking included). |
| `LLM_TIMEOUT_SECONDS` | 300 | Timeout per LLM call. |
| `BEDROCK_TEMPERATURE` | unset | Only for models that accept sampling parameters; Opus 5.5 and Sonnet 5.5 reject it. |
| `ENABLE_WEB_SEARCH` | true | DuckDuckGo tool for the chat. |
| `SESSION_STORAGE` | memory | `memory` or `file` (JSON per session in `SESSION_STORAGE_PATH`). |
| `SESSION_TTL_MINUTES` | 120 | Time after which sessions and their documents are deleted. |
| `MAX_CONCURRENT_JOBS` | 3 | Jobs analyzed in parallel. |
| `FRONTEND_ORIGINS` | localhost:8501 | CORS origins, comma separated. |
| `FIT_WEIGHTS__MUST_HAVE_REQUIREMENTS` | 0.40 | Aggregator weights (see `FitWeights`). |
| `THRESHOLDS__CLAIM_SUPPORTED` | 0.60 | Jev threshold for a claim to count as supported (see `ValidationThresholds`). |
| `RECOMMENDATION_THRESHOLDS__APPLY_SCORE` | 72 | Score cut-offs for the recommendation. |
| `TYPESAFE_DEFAULT_MODEL` | jev-latest | Pin a version such as `jev-1.13.0` after tuning thresholds. |

## Privacy

- Uploaded files are parsed in memory. Only the extracted text is stored, and it is deleted when the session expires or is deleted. Rendered CVs live in an in-memory cache that is cleared at the same time.
- Logs are JSON lines with ids, counts and statuses. Logs never contain API keys or document contents.
- Job ingestion respects `robots.txt` and detects login walls and captchas. It does not use login bypass, proxy rotation or anti-bot evasion. When a page cannot be read, the API returns `needs_manual_paste` for that job and the UI asks you to paste the description.

## Assumptions and decisions

These are the points where the Jev, Bedrock or Groq documentation left a choice open:

1. **SDK package:** the docs install `typesafe-sdk` (import `typesafe_sdk`, version 0.7.2 at the time of writing). The client is `AsyncTypeSafeClient(api_key=..., model=..., base_url=..., retry=RetryPolicy(...), timeout=...)`, and `TypeSafeError` / `TypeSafeAPIError` are caught and mapped to app errors.
2. **Score keys:** the SDK returns Score `legend` and `probabilities` keyed by integers, while the HTTP docs show strings. `JevResponseTranslator` normalizes them to strings.
3. **Noul confidence:** the API returns no `confidence` for Noul answers, because the probability already carries the uncertainty. The app derives `confidence = |2p - 1|` for display and low-confidence flags. Choice and Score use the confidence the API returns.
4. **State size:** Jev 1.13 allows 32k tokens for the state plus the longest question, and 64k in total. The app limits the state to `JEV_MAX_STATE_CHARS` (60,000 characters, about 15k tokens), chunks evidence for requirement and faithfulness checks, and takes the best chunk. At most `JEV_MAX_QUESTIONS_PER_CALL` questions go in one request.
5. **Counting is done in code:** the Jev jaggedness notes say counting and number handling are weak, so CV length and bullets per role are checked in code.
6. **Bedrock integration:** current Claude models (Opus 5.5, Sonnet 5.5, Fable 5.1 and others) are not served by the Bedrock `Converse` API, so `ChatBedrockConverse` cannot be used. The app calls the Messages API endpoint of Claude in Amazon Bedrock (`https://bedrock-mantle.{region}.api.aws/anthropic`) through `langchain-anthropic`'s `ChatAnthropic`, passing the Bedrock API key as the bearer token. This path supports bearer-token authentication only; SigV4 or IAM-role authentication would need Anthropic's `AnthropicBedrockMantle` client. Older models with versioned ids (for example `anthropic.claude-sonnet-4-5-20250929-v1:0`) are not on that endpoint; for those the app switches automatically to the Bedrock `Converse` API (`langchain-aws`'s `ChatBedrockConverse`, same API key), and adds the cross-region inference profile prefix from the region (`us.`, `eu.` or `global.`) when the id has none. Force a route with `BEDROCK_API=messages|converse`. Accounts without access to the newer models get a 403 on the Messages endpoint; use a versioned id in that case.
7. **Structured output:** structured outputs are not available on Bedrock, and Opus 5.5, Sonnet 5.5 and Fable 5.1 reject forced `tool_choice`. Every extraction therefore binds the Pydantic schema as a tool with `tool_choice=auto`, instructs the model to call it, validates the arguments, and retries with a correction when needed.
8. **Sampling and thinking:** recent Claude models reject `temperature`, so none is sent unless `BEDROCK_TEMPERATURE` is set. Thinking stays on (Opus 5.5 cannot disable it), and the agent history is append-only so thinking blocks stay valid. When the model asks for several tools in one turn, the first one runs and the others get a `SKIPPED` result, instead of the message being edited.
9. **Web search** uses `DuckDuckGoSearchResults` from `langchain-community` (backed by `ddgs`). That package is being sunset upstream. It is isolated behind `WebSearchTool`, so it can be swapped without touching the chat agent.
10. **Spanish, Portuguese and French CVs:** the section splitter recognizes common headings in those languages, and the exported CV uses section headings in the CV's language (the LLM reports it in `TailoredCv.language`). Jev is most accurate in English. Watch the low-confidence badges for other languages.
11. **Real keys:** the test suite runs the full flow with a mocked Jev and a mocked LLM. A full analysis was also run with real Jev and Claude Sonnet 4.5 on Bedrock (Converse route): it finished in 2 iterations, every claim was supported, and ATS alignment improved. The Messages-endpoint route was only checked for authentication and error mapping.
