from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from ui.agent_page import AgentPage
from core.llm_settings import get_verified_models

def test_ui():
    app = QApplication.instance() or QApplication(sys.argv)
    page = AgentPage()

    assert hasattr(page, "chat_model_combo")
    combo = page.chat_model_combo

    print(f"Chat combo item count: {combo.count()}")
    for i in range(combo.count()):
        print(f"  Item {i}: {combo.itemText(i)}")

    # Check that item 0 is Qwen Local (default)
    assert "Qwen" in combo.itemText(0)
    assert combo.currentIndex() == 0

    # Last item is Configure option
    last_idx = combo.count() - 1
    last_data = combo.itemData(last_idx)
    assert isinstance(last_data, dict)
    assert last_data.get("action") == "configure"

    print("ALL UI TESTS PASSED!")

if __name__ == "__main__":
    test_ui()
