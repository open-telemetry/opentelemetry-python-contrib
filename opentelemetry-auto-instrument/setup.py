from setuptools import setup
from setuptools.command.build_py import build_py
from pathlib import Path


class build_py_with_pth_file(build_py):
    def run(self) -> None:
        super().run()
        build_path = Path(self.build_lib)
        out = build_path / "opentelemetry_auto_instrument.pth"
        out.write_text("import opentelemetry.instrumentation.auto_instrumentation.auto_instrument_on_import")


setup(
    cmdclass={"build_py": build_py_with_pth_file},
)
