import json
import logging
from typing import Dict, Any, Optional
import requests
from flask import current_app

logger = logging.getLogger(__name__)


INVESTIGATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "root_cause": {"type": "string"},
        "explanation": {"type": "string"},
        "evidence_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "expected": {"type": "string"},
                    "actual": {"type": "string"},
                    "source_id": {"type": "string"},
                    "note": {"type": "string"}
                },
                "required": ["field", "expected", "actual", "source_id"]
            }
        },
        "alternative_hypotheses": {
            "type": "array",
            "items": {"type": "string"}
        },
        "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "priority_rationale": {"type": "string"},
        "recommended_action_type": {
            "type": "string",
            "enum": [
                "CREATE_FOLLOW_UP_TASK",
                "DRAFT_REFUND_INQUIRY",
                "PROPOSED_RECONCILIATION_ADJUSTMENT",
                "FLAG_SUSPECTED_DUPLICATE"
            ]
        },
        "recommended_action_payload": {"type": "object"},
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 100}
    },
    "required": [
        "summary", "root_cause", "explanation", "evidence_items",
        "alternative_hypotheses", "priority", "priority_rationale",
        "recommended_action_type", "recommended_action_payload", "confidence_score"
    ]
}


class LLMAdapter:
    """
    Adapter for configurable LLM providers with timeout and deterministic fallback.
    Never pretends a rule-based result came from an LLM.
    """

    @classmethod
    def is_configured(cls) -> bool:
        provider = current_app.config.get('LLM_PROVIDER', 'none').lower()
        api_key = current_app.config.get('LLM_API_KEY', '').strip()
        return provider in ('openai', 'anthropic', 'gemini') and bool(api_key)

    @classmethod
    def investigate(cls, prompt_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Invokes configured LLM provider. Returns strictly validated JSON or None if unconfigured/failed.
        """
        if not cls.is_configured():
            return None

        provider = current_app.config.get('LLM_PROVIDER', '').lower()
        api_key = current_app.config.get('LLM_API_KEY', '')
        model = current_app.config.get('LLM_MODEL', 'gpt-4o-mini')

        system_prompt = (
            "You are GhostLedger AI, a senior fintech reconciliation auditor.\n"
            "Analyze the financial discrepancy factually based solely on the database records provided.\n"
            "Never invent evidence, never hallucinate transaction IDs, and never assume missing facts.\n"
            "Output MUST be valid JSON conforming to the requested schema."
        )

        user_content = (
            f"Discrepancy Details:\n{json.dumps(prompt_data, indent=2)}\n\n"
            f"Produce structured JSON with keys: summary, root_cause, explanation, evidence_items, "
            f"alternative_hypotheses, priority (HIGH|MEDIUM|LOW), priority_rationale, "
            f"recommended_action_type, recommended_action_payload, confidence_score."
        )

        try:
            if provider == 'openai':
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content}
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.0
                    },
                    timeout=12
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data['choices'][0]['message']['content']
                    parsed = json.loads(content)
                    parsed['engine_used'] = 'LLM_AGENT'
                    parsed['model_name'] = model
                    return cls.validate_output_schema(parsed)
                else:
                    logger.warning(f"OpenAI API error {resp.status_code}: {resp.text}")
                    return None

            elif provider == 'gemini':
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                resp = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_content}"}]}],
                        "generationConfig": {"response_mime_type": "application/json"}
                    },
                    timeout=12
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    parsed = json.loads(text)
                    parsed['engine_used'] = 'LLM_AGENT'
                    parsed['model_name'] = model
                    return cls.validate_output_schema(parsed)
                else:
                    logger.warning(f"Gemini API error {resp.status_code}: {resp.text}")
                    return None

        except Exception as e:
            logger.warning(f"LLM request error: {str(e)}. Gracefully falling back to deterministic rules engine.")
            return None

        return None

    @classmethod
    def validate_output_schema(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates output against required fields and structure.
        """
        required_keys = [
            'summary', 'root_cause', 'explanation', 'evidence_items',
            'alternative_hypotheses', 'priority', 'priority_rationale',
            'recommended_action_type', 'recommended_action_payload', 'confidence_score'
        ]
        for k in required_keys:
            if k not in data:
                raise ValueError(f"LLM output missing required key: {k}")

        if data['priority'] not in ('HIGH', 'MEDIUM', 'LOW'):
            data['priority'] = 'MEDIUM'

        allowed_actions = {
            'CREATE_FOLLOW_UP_TASK',
            'DRAFT_REFUND_INQUIRY',
            'PROPOSED_RECONCILIATION_ADJUSTMENT',
            'FLAG_SUSPECTED_DUPLICATE'
        }
        if data['recommended_action_type'] not in allowed_actions:
            data['recommended_action_type'] = 'CREATE_FOLLOW_UP_TASK'

        data['confidence_score'] = max(0.0, min(100.0, float(data.get('confidence_score', 80.0))))
        return data
