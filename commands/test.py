import sys
import unittest

from libs.config import ROOT_DIR


def run():
    suite = unittest.defaultTestLoader.discover(str(ROOT_DIR / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
