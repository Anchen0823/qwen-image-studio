"""Discover the installed workbench and delegate to its JSON CLI."""
import os
import runpy
import sys
from pathlib import Path

configured = os.environ.get('QWEN_WORKBENCH')
candidates = [Path(configured)] if configured else [*Path(__file__).resolve().parents, Path(r'D:\users\self_projects\qwen_')]
workspace = next((path for path in candidates if (path / 'qwen_cli.py').is_file()), None)
if workspace is None:
    sys.exit('Set QWEN_WORKBENCH to the folder containing qwen_cli.py.')
sys.path.insert(0, str(workspace))
runpy.run_path(str(workspace / 'qwen_cli.py'), run_name='__main__')
