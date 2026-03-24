"""
Assembler - Context assembly for LLM prompts.

Phase 04: Assembly
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ContextBlock:
    """A block of context content."""
    content: str
    block_type: str = "text"
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def render(self) -> str:
        """Render the block to string."""
        return self.content


@dataclass
class AssembledContext:
    """Result of context assembly."""
    prompt: str
    blocks: List[ContextBlock] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    assembled_at: datetime = field(default_factory=datetime.now)
    
    @property
    def token_estimate(self) -> int:
        """Estimate token count (rough approximation)."""
        return len(self.prompt.split()) * 1.3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "prompt": self.prompt,
            "block_count": len(self.blocks),
            "token_estimate": self.token_estimate,
            "metadata": self.metadata,
            "assembled_at": self.assembled_at.isoformat(),
        }


class ContextAssembler:
    """
    Assembles context from multiple sources into a coherent prompt.
    
    Phase 04: Basic assembly with weighted blocks and templates.
    """
    
    def __init__(self, system_prompt: Optional[str] = None):
        self.system_prompt = system_prompt or "You are a helpful assistant."
        self._blocks: List[ContextBlock] = []
        self._templates: Dict[str, str] = {}
    
    def add_block(self, content: str, block_type: str = "text",
                  weight: float = 1.0, metadata: Optional[Dict[str, Any]] = None) -> "ContextAssembler":
        """
        Add a context block.
        
        Args:
            content: The block content
            block_type: Type of block (text, code, history, etc.)
            weight: Importance weight for ordering
            metadata: Optional metadata
        
        Returns:
            Self for chaining
        """
        block = ContextBlock(
            content=content,
            block_type=block_type,
            weight=weight,
            metadata=metadata or {},
        )
        self._blocks.append(block)
        return self
    
    def add_system_context(self, content: str) -> "ContextAssembler":
        """Add system-level context (high weight)."""
        return self.add_block(content, block_type="system", weight=2.0)
    
    def add_user_context(self, content: str) -> "ContextAssembler":
        """Add user-provided context."""
        return self.add_block(content, block_type="user", weight=1.5)
    
    def add_history(self, messages: List[Dict[str, str]]) -> "ContextAssembler":
        """Add conversation history."""
        history_text = self._format_history(messages)
        return self.add_block(history_text, block_type="history", weight=1.0)
    
    def add_knowledge(self, facts: List[str]) -> "ContextAssembler":
        """Add knowledge base facts."""
        facts_text = "\n".join(f"- {fact}" for fact in facts)
        return self.add_block(facts_text, block_type="knowledge", weight=1.2)
    
    def add_code_context(self, code: str, language: str = "python") -> "ContextAssembler":
        """Add code context."""
        formatted = f"```{language}\n{code}\n```"
        return self.add_block(formatted, block_type="code", weight=1.0)
    
    def register_template(self, name: str, template: str) -> None:
        """Register a template for reuse."""
        self._templates[name] = template
    
    def use_template(self, name: str, **kwargs: Any) -> "ContextAssembler":
        """Use a registered template with variable substitution."""
        if name not in self._templates:
            raise ValueError(f"Template not found: {name}")
        
        template = self._templates[name]
        content = template.format(**kwargs)
        return self.add_block(content, block_type="template")
    
    def assemble(self, user_message: Optional[str] = None) -> AssembledContext:
        """
        Assemble all context into a final prompt.
        
        Args:
            user_message: Optional user message to append
        
        Returns:
            AssembledContext with the final prompt
        """
        # Sort blocks by weight (descending)
        sorted_blocks = sorted(self._blocks, key=lambda b: b.weight, reverse=True)
        
        # Build the prompt
        sections = []
        
        # System prompt first
        sections.append(f"<system>\n{self.system_prompt}\n</system>\n")
        
        # Add blocks by type
        for block_type in ["system", "knowledge", "user", "history", "code", "template", "text"]:
            type_blocks = [b for b in sorted_blocks if b.block_type == block_type]
            if type_blocks:
                section_content = "\n\n".join(b.render() for b in type_blocks)
                sections.append(f"<{block_type}>\n{section_content}\n</{block_type}>")
        
        # Add user message if provided
        if user_message:
            sections.append(f"<user_message>\n{user_message}\n</user_message>")
        
        prompt = "\n\n".join(sections)
        
        return AssembledContext(
            prompt=prompt,
            blocks=list(self._blocks),
            metadata={"block_types": list(set(b.block_type for b in self._blocks))},
        )
    
    def clear(self) -> "ContextAssembler":
        """Clear all blocks."""
        self._blocks.clear()
        return self
    
    def _format_history(self, messages: List[Dict[str, str]]) -> str:
        """Format conversation history."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)


class PromptBuilder:
    """
    Fluent interface for building prompts.
    
    Simpler alternative to ContextAssembler for straightforward prompts.
    """
    
    def __init__(self):
        self._parts: List[str] = []
        self._variables: Dict[str, Any] = {}
    
    def system(self, text: str) -> "PromptBuilder":
        """Add system instruction."""
        self._parts.append(f"[SYSTEM]: {text}")
        return self
    
    def context(self, text: str) -> "PromptBuilder":
        """Add context."""
        self._parts.append(f"[CONTEXT]: {text}")
        return self
    
    def instruction(self, text: str) -> "PromptBuilder":
        """Add instruction."""
        self._parts.append(f"[INSTRUCTION]: {text}")
        return self
    
    def example(self, input_text: str, output_text: str) -> "PromptBuilder":
        """Add an example."""
        self._parts.append(f"[EXAMPLE]\nInput: {input_text}\nOutput: {output_text}")
        return self
    
    def variable(self, name: str, value: Any) -> "PromptBuilder":
        """Set a variable for substitution."""
        self._variables[name] = value
        return self
    
    def build(self) -> str:
        """Build the final prompt with variable substitution."""
        prompt = "\n\n".join(self._parts)

        # Substitute variables
        for name, value in self._variables.items():
            prompt = prompt.replace(f"{{{name}}}", str(value))

        return prompt


def check_pressure_and_evict(db: Any, contract: Any,
                              evict_ratio: float = 0.85
                              ) -> None:
    """
    Check VRAM pressure and evict lowest-scoring
    hot chunks if utilization exceeds evict_ratio.
    
    Args:
        db: Vector database with hot_chunks
        contract: MemoryContract with vector_max_mb
        evict_ratio: Threshold for eviction (default 0.85 = 85%)
    """
    if db is None or contract is None:
        return

    # Get current utilization
    try:
        if not hasattr(db, 'hot_chunks'):
            return
        if not db.hot_chunks:
            return

        # Calculate utilization
        vram_used = (
            db.get_hot_vram_mb()
            if hasattr(db, 'get_hot_vram_mb')
            else len(db.hot_chunks) * 0.01
        )
        vram_max = (
            contract.vector_max_mb
            if hasattr(contract, 'vector_max_mb')
            else float('inf')
        )

        if vram_max == 0 or vram_max == float('inf'):
            return

        utilization = vram_used / vram_max

        if utilization <= evict_ratio:
            return  # pressure is fine

        # Evict bottom 20% by last_score
        import logging
        logging.info(
            f"[ENGRAM] pressure check: "
            f"{utilization:.1%} > {evict_ratio:.1%} "
            f"— evicting low-score chunks"
        )

        sorted_chunks = sorted(
            db.hot_chunks,
            key=lambda c: getattr(c, 'last_score', 0.0)
        )
        evict_count = max(1, len(sorted_chunks) // 5)

        for chunk in sorted_chunks[:evict_count]:
            if hasattr(db, 'demote'):
                db.demote(chunk.id)
                logging.debug(
                    f"[ENGRAM] evicted: {chunk.id} "
                    f"(score: {chunk.last_score:.3f})"
                )

    except Exception as e:
        import logging
        logging.warning(
            f"[ENGRAM] check_pressure_and_evict error: {e}"
        )
