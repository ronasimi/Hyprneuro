"""Fixed isolated GTK bridge entry; no ambient import path or startup consent."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hyprneuro.pi_desktop_bridge import main

if __name__=='__main__':
    raise SystemExit(main())
