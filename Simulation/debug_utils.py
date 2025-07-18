import os
import sys
import traceback

def debug_print(msg):
    if os.environ.get("TOSSIM_DEBUG") == "1":
        print(f"[DEBUG] {msg}", file=sys.stderr)

def debug_exception(context=None):
    if os.environ.get("TOSSIM_DEBUG") == "1":
        print(f"[DEBUG-EXCEPTION] {context if context else ''}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr) 