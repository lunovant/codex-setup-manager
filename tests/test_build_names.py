import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("build_script", Path(__file__).resolve().parents[1] / "scripts" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def test_artifact_names_use_lunovant_prefix():
    assert build.exe_name().startswith("lunovant-setup-")
    assert build.app_zip_path().name.startswith("lunovant-setup-macos-")
    assert build.app_path().name == "Lunovant Setup.app"
