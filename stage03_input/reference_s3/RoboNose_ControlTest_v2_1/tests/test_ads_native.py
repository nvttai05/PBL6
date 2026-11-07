import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class AdsNativeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("g++"), "Optional native driver test requires g++")
    def test_mux_scale_signed_counts_and_failures(self):
        root = Path(__file__).resolve().parents[1]
        native = root / "tests" / "native"
        firmware = root / "firmware" / "RoboNose_SensorTest"
        with tempfile.TemporaryDirectory() as tmp:
            program = Path(tmp) / "test_ads"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(native), "-I", str(firmware),
                            str(native / "test_ads.cpp"), str(firmware / "ads1115_reader.cpp"),
                            "-o", str(program)], check=True, capture_output=True)
            subprocess.run([str(program)], check=True, capture_output=True)
