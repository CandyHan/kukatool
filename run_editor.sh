#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
export MPLBACKEND=TkAgg
python kuka_gui_editor.py
