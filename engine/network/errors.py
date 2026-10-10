"""The one error type the warm path raises. Like ConfigError and
ArchiveError, it always names the file, line, or value and the fix, so a
person lands at their own data rather than in this package."""


class NetworkError(Exception):
    """Anything wrong with config/network/: an unreadable export, a malformed
    people file or touch row, an alias file of the wrong shape."""
