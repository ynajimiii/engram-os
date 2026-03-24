"""
Tests for contract.py - Interface definitions and type contracts.

Phase 00: Foundation
"""

import pytest
from engram.core.contract import (
    Contract,
    ContractViolationError,
    SessionContract,
    AgentContract,
    MessageContract,
)


class TestContract:
    """Tests for base Contract class."""

    def test_contract_creation(self):
        """Test creating a basic contract."""
        contract = Contract(
            name="TestContract",
            required_fields=["field1", "field2"],
            optional_fields=["field3"],
        )
        
        assert contract.name == "TestContract"
        assert contract.required_fields == ["field1", "field2"]
        assert contract.optional_fields == ["field3"]

    def test_contract_validate_success(self):
        """Test validation with all required fields present."""
        contract = Contract(
            name="TestContract",
            required_fields=["field1", "field2"],
        )
        
        data = {"field1": "value1", "field2": "value2", "extra": "value3"}
        assert contract.validate(data) is True

    def test_contract_validate_missing_field(self):
        """Test validation fails with missing required field."""
        contract = Contract(
            name="TestContract",
            required_fields=["field1", "field2"],
        )
        
        data = {"field1": "value1"}
        
        with pytest.raises(ContractViolationError) as exc_info:
            contract.validate(data)
        
        assert "field2" in str(exc_info.value)

    def test_contract_validate_empty(self):
        """Test validation with no required fields."""
        contract = Contract(name="EmptyContract")
        
        assert contract.validate({}) is True
        assert contract.validate({"any": "data"}) is True


class TestSessionContract:
    """Tests for SessionContract."""

    def test_session_contract_required_fields(self):
        """Test SessionContract has correct required fields."""
        contract = SessionContract()
        
        assert "session_id" in contract.required_fields
        assert "created_at" in contract.required_fields

    def test_session_contract_validate(self):
        """Test SessionContract validation."""
        contract = SessionContract()
        
        valid_data = {
            "session_id": "abc123",
            "created_at": "2024-01-01T00:00:00",
        }
        assert contract.validate(valid_data) is True

    def test_session_contract_missing(self):
        """Test SessionContract fails with missing fields."""
        contract = SessionContract()
        
        with pytest.raises(ContractViolationError):
            contract.validate({"session_id": "abc123"})


class TestAgentContract:
    """Tests for AgentContract."""

    def test_agent_contract_required_fields(self):
        """Test AgentContract has correct required fields."""
        contract = AgentContract()
        
        assert "agent_id" in contract.required_fields
        assert "name" in contract.required_fields

    def test_agent_contract_validate(self):
        """Test AgentContract validation."""
        contract = AgentContract()
        
        valid_data = {
            "agent_id": "agent_1",
            "name": "TestAgent",
        }
        assert contract.validate(valid_data) is True


class TestMessageContract:
    """Tests for MessageContract."""

    def test_message_contract_required_fields(self):
        """Test MessageContract has correct required fields."""
        contract = MessageContract()
        
        assert "role" in contract.required_fields
        assert "content" in contract.required_fields

    def test_message_contract_validate(self):
        """Test MessageContract validation."""
        contract = MessageContract()
        
        valid_data = {
            "role": "user",
            "content": "Hello!",
        }
        assert contract.validate(valid_data) is True

    def test_message_contract_missing_content(self):
        """Test MessageContract fails without content."""
        contract = MessageContract()
        
        with pytest.raises(ContractViolationError):
            contract.validate({"role": "user"})
