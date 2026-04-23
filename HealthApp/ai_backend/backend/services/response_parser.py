"""
Response parser for extracting structured data from LLM responses.
Validates: Requirements 6.1, 6.2, 7.4, 7.5
"""

import json
import logging
import re
from typing import Optional

from models.schemas import StructuredResponse

logger = logging.getLogger(__name__)


class ResponseParser:

    def parse(self, full_response: str) -> tuple[str, Optional[StructuredResponse], list[str]]:
        """
        Returns: (clean_text, structured_or_none, suggestions)
        """
        logger.debug(f"🔍 Parsing response (length: {len(full_response)})")

        # Extract suggestions first (trước khi strip bất cứ thứ gì)
        suggestions = self._extract_suggestions(full_response)

        # Strip toàn bộ SUGGESTIONS block (mọi variant LLM có thể viết)
        clean = self._strip_suggestions(full_response)

        # Extract action block
        action_json = self._extract_action_block(clean)

        if not action_json:
            logger.debug("ℹ️  No action data to parse")
            return (clean, None, suggestions)

        logger.debug(f"📦 Action JSON to parse: {action_json[:300]}...")

        try:
            data = json.loads(action_json)
            structured = self._validate_structured_response(data)

            if structured:
                clean_text = self._remove_all_blocks(clean)
                logger.info("✅ Parsed structured response with %d actions", len(structured.actions))
                return (clean_text, structured, suggestions)
            else:
                logger.warning("⚠️  Action block found but validation failed")
                return (self._remove_all_blocks(clean), None, suggestions)

        except json.JSONDecodeError as e:
            logger.warning("⚠️  Invalid JSON in action block: %s", e)
            logger.debug(f"📄 Raw JSON: {action_json[:500]}")
            
            # Try multiple fix strategies
            fixed_json = None
            
            # Strategy 1: Truncate at last valid }
            try:
                last_brace = action_json.rfind('}')
                if last_brace > 0:
                    fixed = action_json[:last_brace + 1]
                    data = json.loads(fixed)
                    structured = self._validate_structured_response(data)
                    if structured:
                        clean_text = self._remove_all_blocks(clean)
                        logger.info("✅ Parsed after truncating JSON (%d actions)", len(structured.actions))
                        return (clean_text, structured, suggestions)
            except Exception:
                pass
            
            # Strategy 2: Try to fix common issues (trailing commas, missing quotes)
            try:
                # Remove trailing commas before } or ]
                fixed = re.sub(r',(\s*[}\]])', r'\1', action_json)
                data = json.loads(fixed)
                structured = self._validate_structured_response(data)
                if structured:
                    clean_text = self._remove_all_blocks(clean)
                    logger.info("✅ Parsed after fixing commas (%d actions)", len(structured.actions))
                    return (clean_text, structured, suggestions)
            except Exception:
                pass
            
            # Strategy 3: Extract just the actions array if visible
            try:
                actions_match = re.search(r'"actions"\s*:\s*(\[.*?\])', action_json, re.DOTALL)
                if actions_match:
                    actions_json = actions_match.group(1)
                    actions = json.loads(actions_json)
                    data = {
                        "type": "structured",
                        "text": "",
                        "actions": actions
                    }
                    structured = self._validate_structured_response(data)
                    if structured:
                        clean_text = self._remove_all_blocks(clean)
                        logger.info("✅ Parsed by extracting actions array (%d actions)", len(structured.actions))
                        return (clean_text, structured, suggestions)
            except Exception as retry_err:
                logger.warning("⚠️  All fix strategies failed: %s", retry_err)

            return (self._remove_all_blocks(clean), None, suggestions)

    def _extract_suggestions(self, text: str) -> list[str]:
        """
        Extract suggestions từ mọi variant LLM có thể viết:
        - [SUGGESTIONS]...[/SUGGESTIONS]
        - SUGGESTIONS\n...\n[/SUGGESTIONS]
        - **SUGGESTIONS**\n...
        """
        # Variant 1: proper tag [SUGGESTIONS]...[/SUGGESTIONS]
        match = re.search(
            r'\[SUGGESTIONS\]\s*(.*?)\s*\[/SUGGESTIONS\]',
            text, re.DOTALL | re.IGNORECASE
        )
        # Variant 2: không có [ ở đầu — "SUGGESTIONS\n[...]\n[/SUGGESTIONS]"
        if not match:
            match = re.search(
                r'(?<!\[)SUGGESTIONS\]?\s*(.*?)\s*\[?/SUGGESTIONS\]?',
                text, re.DOTALL | re.IGNORECASE
            )
        # Variant 3: **SUGGESTIONS**
        if not match:
            match = re.search(
                r'\*\*SUGGESTIONS\*\*\s*(.*?)(?:\*\*/SUGGESTIONS\*\*|$)',
                text, re.DOTALL | re.IGNORECASE
            )
        if not match:
            return []
        try:
            raw = match.group(1).strip()
            first = raw.find('[')
            last = raw.rfind(']')
            if first == -1 or last == -1:
                return []
            suggestions = json.loads(raw[first:last + 1])
            return [s for s in suggestions if isinstance(s, str)][:4]
        except Exception:
            return []

    def _strip_suggestions(self, text: str) -> str:
        """
        Xóa toàn bộ SUGGESTIONS block khỏi text — mọi variant LLM có thể viết.
        Đây là bước quan trọng để không hiển thị raw tag ra UI.
        """
        result = text
        # Variant 1: [SUGGESTIONS]...[/SUGGESTIONS]
        result = re.sub(
            r'\[SUGGESTIONS\].*?\[/SUGGESTIONS\]',
            '', result, flags=re.DOTALL | re.IGNORECASE
        )
        # Variant 2: "SUGGESTIONS\n[...]\n[/SUGGESTIONS]" (thiếu [ ở đầu)
        result = re.sub(
            r'(?<!\[)SUGGESTIONS\]?\s*\[.*?\]\s*\[?/?SUGGESTIONS\]?',
            '', result, flags=re.DOTALL | re.IGNORECASE
        )
        # Variant 3: **SUGGESTIONS**...**[/SUGGESTIONS]**
        result = re.sub(
            r'\*\*SUGGESTIONS\*\*.*?(?:\*\*/SUGGESTIONS\*\*|\Z)',
            '', result, flags=re.DOTALL | re.IGNORECASE
        )
        # Variant 4: dòng chỉ chứa "SUGGESTIONS" hoặc "[/SUGGESTIONS]" còn sót
        result = re.sub(
            r'^\s*\[?/?SUGGESTIONS\]?\s*$',
            '', result, flags=re.MULTILINE | re.IGNORECASE
        )
        return result.strip()

    def _remove_all_blocks(self, text: str) -> str:
        """Remove all [TAG]...[/TAG] and **TAG**...{} blocks, bao gồm SUGGESTIONS"""
        result = text
        for tag in ['ACTION_DATA', 'CUSTOM_DATA', 'STRUCTURED_DATA', 'DATA', 'SUGGESTIONS']:
            result = re.sub(rf'\[{tag}\].*?\[/{tag}\]', '', result,
                            flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(
            r'\*\*(?:ACTION_DATA|CUSTOM_DATA|STRUCTURED_DATA|DATA)\*\*\s*\{.*\}',
            '', result, flags=re.DOTALL | re.IGNORECASE
        )
        result = re.sub(
            r'\{\s*"type"\s*:\s*"structured".*\}', '', result, flags=re.DOTALL
        )
        # Strip SUGGESTIONS variants còn sót
        result = self._strip_suggestions(result)
        # Strip dòng trống thừa
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    def _extract_action_block(self, text: str) -> Optional[str]:
        """
        Extract JSON string from action data block.
        Handles all variants the LLM might generate:
        - [ACTION_DATA]...[/ACTION_DATA]
        - **ACTION_DATA**...
        - [CUSTOM_DATA]...[/CUSTOM_DATA]
        - etc.
        """
        # Pattern 1: proper tag variants [TAG]...[/TAG]
        tag_patterns = [
            r'\[ACTION_DATA\]\s*(.*?)\s*\[/ACTION_DATA\]',
            r'\[CUSTOM_DATA\]\s*(.*?)\s*\[/CUSTOM_DATA\]',
            r'\[STRUCTURED_DATA\]\s*(.*?)\s*\[/STRUCTURED_DATA\]',
            r'\[DATA\]\s*(.*?)\s*\[/DATA\]',
        ]
        for pattern in tag_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return self._clean_json(match.group(1))

        # Pattern 2: markdown bold **TAG**...{ json } (LLM dùng ** thay vì [])
        bold_match = re.search(
            r'\*\*(?:ACTION_DATA|CUSTOM_DATA|STRUCTURED_DATA|DATA)\*\*\s*(\{.*)',
            text, re.DOTALL | re.IGNORECASE
        )
        if bold_match:
            return self._clean_json(bold_match.group(1))

        # Pattern 3: bare JSON block với "type": "structured" (không có tag)
        bare_match = re.search(
            r'(\{\s*"type"\s*:\s*"structured".*\})',
            text, re.DOTALL
        )
        if bare_match:
            return self._clean_json(bare_match.group(1))

        logger.debug("ℹ️  No action block found in response")
        return None

    def _clean_json(self, raw: str) -> Optional[str]:
        """Làm sạch JSON string: trim, cắt từ { đến } cuối, xử lý nested objects"""
        raw = raw.strip()
        first = raw.find('{')
        if first == -1:
            return None
        
        # Tìm } cuối cùng matching với { đầu tiên
        # Đếm số lượng { và } để tìm đúng closing brace
        brace_count = 0
        last = -1
        for i in range(first, len(raw)):
            if raw[i] == '{':
                brace_count += 1
            elif raw[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    last = i
                    break
        
        if last == -1:
            # Không tìm thấy closing brace, thử dùng rfind
            last = raw.rfind('}')
            if last == -1:
                return None
        
        cleaned = raw[first:last + 1]
        logger.debug(f"📦 Extracted JSON ({len(cleaned)} chars): {cleaned[:200]}...")
        return cleaned

    def _validate_structured_response(self, data: dict) -> Optional[StructuredResponse]:
        """
        Validate and parse JSON dict into StructuredResponse Pydantic model.
        Auto-fix common LLM mistakes before validating.
        """
        try:
            # Auto-fix: LLM hay dùng type khác thay vì "structured"
            if "type" not in data or data["type"] != "structured":
                data["type"] = "structured"

            # Auto-fix: LLM hay dùng "items" thay vì "actions"
            if "actions" not in data and "items" in data:
                data["actions"] = data.pop("items")

            # Auto-fix: thiếu "text" field
            if "text" not in data:
                data["text"] = ""

            # Auto-fix: actions là list của dicts, normalize từng item
            if "actions" in data and isinstance(data["actions"], list):
                fixed_actions = []
                for item in data["actions"]:
                    if not isinstance(item, dict):
                        continue
                    # Auto-fix kind field
                    if "kind" not in item:
                        item["kind"] = "exercise" if "duration" in item.get("details", {}) else "food"
                    # Auto-fix wger_id
                    if "wger_id" not in item:
                        item["wger_id"] = 0
                    # Auto-fix details
                    if "details" not in item:
                        item["details"] = {}
                    fixed_actions.append(item)
                data["actions"] = fixed_actions

            structured = StructuredResponse(**data)
            return structured
        except Exception as e:
            logger.warning("⚠️  Failed to validate structured response: %s", e)
            return None


# Singleton instance
response_parser = ResponseParser()
