"""
Unit tests for ResponseParser
Tests Requirements 6.1, 6.2, 7.4, 7.5
"""

import pytest
from services.response_parser import ResponseParser


def test_parse_no_action_block():
    """Test parsing response without ACTION_DATA block"""
    parser = ResponseParser()
    text = "Đây là câu trả lời thông thường không có action block."
    
    clean_text, structured = parser.parse(text)
    
    assert clean_text == text
    assert structured is None


def test_parse_with_valid_action_block():
    """Test parsing response with valid ACTION_DATA block"""
    parser = ResponseParser()
    text = """Đây là câu trả lời với action block.

[ACTION_DATA]
{"type": "structured", "text": "Test", "actions": [{"kind": "exercise", "wger_id": 123, "name": "Push-up", "details": {"duration": 30, "calories_burned": 150, "type": "strength"}}]}
[/ACTION_DATA]"""
    
    clean_text, structured = parser.parse(text)
    
    assert "[ACTION_DATA]" not in clean_text
    assert "[/ACTION_DATA]" not in clean_text
    assert "Đây là câu trả lời với action block." in clean_text
    assert structured is not None
    assert structured.type == "structured"
    assert len(structured.actions) == 1
    assert structured.actions[0].kind == "exercise"
    assert structured.actions[0].wger_id == 123


def test_parse_with_invalid_json():
    """Test parsing response with malformed JSON in ACTION_DATA"""
    parser = ResponseParser()
    text = """Câu trả lời.

[ACTION_DATA]
{invalid json}
[/ACTION_DATA]"""
    
    clean_text, structured = parser.parse(text)
    
    # Should return original text when JSON is invalid
    assert clean_text == text
    assert structured is None


def test_parse_with_invalid_schema():
    """Test parsing response with JSON that doesn't match StructuredResponse schema"""
    parser = ResponseParser()
    text = """Câu trả lời.

[ACTION_DATA]
{"wrong": "schema"}
[/ACTION_DATA]"""
    
    clean_text, structured = parser.parse(text)
    
    # Should return original text when schema validation fails
    assert clean_text == text
    assert structured is None


def test_extract_action_block():
    """Test _extract_action_block method"""
    parser = ResponseParser()
    
    # Test with action block
    text = "Before [ACTION_DATA]content[/ACTION_DATA] After"
    result = parser._extract_action_block(text)
    assert result == "content"
    
    # Test without action block
    text = "No action block here"
    result = parser._extract_action_block(text)
    assert result is None
    
    # Test with multiline content
    text = """Before
[ACTION_DATA]
line1
line2
[/ACTION_DATA]
After"""
    result = parser._extract_action_block(text)
    assert "line1" in result
    assert "line2" in result


def test_parse_food_action():
    """Test parsing response with food action"""
    parser = ResponseParser()
    text = """Gợi ý món ăn cho bạn.

[ACTION_DATA]
{"type": "structured", "text": "Food suggestion", "actions": [{"kind": "food", "wger_id": 456, "name": "Chicken Breast", "details": {"calories": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "meal_type": "lunch"}}]}
[/ACTION_DATA]"""
    
    clean_text, structured = parser.parse(text)
    
    assert structured is not None
    assert len(structured.actions) == 1
    assert structured.actions[0].kind == "food"
    assert structured.actions[0].wger_id == 456
    assert structured.actions[0].name == "Chicken Breast"
    assert structured.actions[0].details["meal_type"] == "lunch"


def test_parse_multiple_actions():
    """Test parsing response with multiple actions"""
    parser = ResponseParser()
    text = """Gợi ý cho bạn.

[ACTION_DATA]
{"type": "structured", "text": "Multiple suggestions", "actions": [{"kind": "exercise", "wger_id": 1, "name": "Push-up", "details": {"duration": 30, "calories_burned": 150, "type": "strength"}}, {"kind": "food", "wger_id": 2, "name": "Banana", "details": {"calories": 89, "protein": 1.1, "carbs": 23.0, "fat": 0.3, "meal_type": "snack"}}]}
[/ACTION_DATA]"""
    
    clean_text, structured = parser.parse(text)
    
    assert structured is not None
    assert len(structured.actions) == 2
    assert structured.actions[0].kind == "exercise"
    assert structured.actions[1].kind == "food"
