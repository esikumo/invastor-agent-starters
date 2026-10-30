"""Single-host, single-process private connection store. POSIX only.
For hosted/multi-worker agents supply your own transactional secret store instead.
Contains plaintext credentials protected by owner-only filesystem permissions.
"""
import fcntl
import json
import os
import stat
import tempfile
from pathlib import Path


class PrivateConnectionStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self._lock = None

    def __enter__(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("Store directory must be owned by you, private (0700), and not a symlink")
        descriptor = os.open(self.directory / "connection.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self._lock = os.fdopen(descriptor, "r+")
        try:
            info = os.fstat(self._lock.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
                raise ValueError("Unsafe connection lock")
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            self._lock.close()
            self._lock = None
            raise
        return self

    def __exit__(self, *args):
        self._lock.close()
        self._lock = None

    def _require_lock(self):
        if self._lock is None:
            raise RuntimeError("Use the store inside a with block for the client's entire lifetime")

    def load(self):
        self._require_lock()
        try:
            descriptor = os.open(self.directory / "connection.json", os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid() or info.st_size > 65536:
                raise ValueError("Unsafe connection file")
            return json.load(stream)

    def save(self, connection):
        self._require_lock()
        descriptor, temporary = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(connection, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / "connection.json")
            descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
