"""
SAM - Autonomous AI Computer Operator for Windows 11
"""

# Auto-register all modules and tools
from sam.config.settings import settings
import sam.monitoring.system_monitor
import sam.computer_use.operator
import sam.coding.coding_agent
import sam.video.video_pipeline
import sam.browser.browser_agent
import sam.documents.doc_engine
import sam.voice.voice_interface
import sam.integrations.app_registry
import sam.agent.models_provider

__version__ = "1.0.0"

