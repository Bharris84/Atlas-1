"""Atlas AI agents.

The agents interpret numbers. They never produce them.
"""

from .agents import (
    AgentOutput,
    Claim,
    research_property,
    run_all_agents,
    strategise,
    underwrite,
)
from .context import build_context, describe_missing, redact_location
from .providers import (
    AIProvider,
    AIProviderError,
    AnthropicProvider,
    Completion,
    NullProvider,
    OpenAIProvider,
    extract_json,
    get_ai_provider,
)

__version__ = "0.1.0"

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AgentOutput",
    "AnthropicProvider",
    "Claim",
    "Completion",
    "NullProvider",
    "OpenAIProvider",
    "build_context",
    "describe_missing",
    "extract_json",
    "get_ai_provider",
    "redact_location",
    "research_property",
    "run_all_agents",
    "strategise",
    "underwrite",
    "__version__",
]
