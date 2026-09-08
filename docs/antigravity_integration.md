# Antigravity and Hermes AI Integration Assessment

Date: 2026-09-08
Repository: aaronwesthoff84/Linux-raycast-ArenaAI
Issue: #5 (Central agent chat)

## Executive Summary

Issue #5 specifies adding central agent chat to ArenaAI with a supported backend, implementing Hermes first, and evaluating the integration semantics of the Antigravity Python SDK.

## Hermes Integration (Primary Implementation)

Hermes Agent exposes an authenticated, OpenAI-compatible HTTP service:
- Reference: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/
- Supported Protocol: Standard REST / JSON and SSE (Server-Sent Events) streaming via `/v1/chat/completions`.
- Endpoints:
  - `POST /v1/chat/completions`: Message exchange supporting `stream: true`, system prompts, temperature, and model selection.
  - `GET /v1/models`: Enumeration of installed and active local models.
- Authentication: Optional/configurable `Bearer <token>` HTTP header.
- Fault tolerance and lifecycle: Supports client cancellation via HTTP connection termination, persistent thread history, and explicit error codes for network/model failures.

## Antigravity Integration Assessment

Google publishes documentation for an Antigravity Python SDK and Gemini API endpoints:
- Reference: https://www.antigravity.google/docs/sdk/overview
- Authentication semantics: Requires explicit credential configuration through an API key (`GEMINI_API_KEY` or `ANTIGRAVITY_API_KEY`) or Google Cloud Application Default Credentials (ADC).
- Session boundaries: The Antigravity IDE and CLI manage their own local session databases and authentication contexts. There is no supported or documented mechanism for an external GTK application to hijack or attach to an existing interactive IDE chat session, nor to reuse an IDE user's account subscription quota without passing valid API credentials.
- Conclusion: ArenaAI must treat Antigravity as an optional, independently authenticated provider requiring explicit API key configuration. It must not imply or promise that running inside an Antigravity environment grants automated session reuse or subscription bypass.
