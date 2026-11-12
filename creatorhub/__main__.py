import sys
from .server import main

main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
