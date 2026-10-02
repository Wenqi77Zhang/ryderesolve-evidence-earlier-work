"""Check the distributable in a fresh environment, without editable source imports."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    work = root / "work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wheel-check-", dir=work) as temp:
        directory = Path(temp)
        assert directory.resolve().is_relative_to(work.resolve())
        wheels = directory / "wheels"
        subprocess.run([sys.executable, "-m", "pip", "wheel", str(root), "--no-deps", "--wheel-dir", str(wheels)], check=True)
        wheel, = wheels.glob("*.whl")
        with zipfile.ZipFile(wheel) as archive:
            assert not any(path.startswith("evaluation/") for path in archive.namelist())
            assert "ryderesolve_evidence/ui.js" in archive.namelist()
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "-c", str(root / "constraints.txt"), str(wheel)], check=True)
        subprocess.run([str(python), "-m", "pip", "check"], check=True)
        check = '''
from pathlib import Path
import ryderesolve_evidence as package
from ryderesolve_evidence import EvidenceTools
tools = EvidenceTools()
assert len(tools.list_cases()) == 2
snapshot = tools.prepare_case("DISP-002")
assert snapshot["audit"]["metrics"]["scheduled_pickup_to_cancellation"]["seconds"] == 360
assert tools.prepare_case("SYN-ROUTE-001")["evidence_pack"]["dispute_type"] == "route_deviation"
root = Path(package.__file__).parent
assert (root / "ui.html").is_file() and (root / "ui.js").is_file()
assert len(list((root / "contracts").glob("*.json"))) == 3
print("Isolated installed wheel passed; both cases, schemas and browser assets present")
'''
        subprocess.run([str(python), "-I", "-c", check], cwd=directory, check=True)


if __name__ == "__main__":
    main()
