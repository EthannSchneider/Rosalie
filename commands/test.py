import os
import sys
import unittest

from libs.config import ROOT_DIR


def run():
    os.environ["LOG_FILE"] = os.devnull   # les tests n'écrivent pas dans le vrai log.txt
    suite = unittest.defaultTestLoader.discover(str(ROOT_DIR / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
