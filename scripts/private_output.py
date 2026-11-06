"""Write private generated files atomically without overwriting their inputs."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


class UnsafeOutputError(ValueError):
    """The requested destination is an input alias or symbolic link."""


@contextmanager
def private_output(output, sources):
    """Yield a mode-0600 text stream and publish it only after success."""
    output = Path(output)
    if output.is_symlink():
        raise UnsafeOutputError("Output must not be a symbolic link")
    for source in sources:
        if output.resolve() == Path(source).resolve() or (
            output.exists() and output.samefile(source)
        ):
            raise UnsafeOutputError("Output must not overwrite a source file")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            yield stream
        # Replacing the directory entry never follows a destination symlink,
        # even if another process created one after the check above.
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
