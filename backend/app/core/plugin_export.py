"""Plugin export utility. Phase D stub — not yet implemented."""
from __future__ import annotations


class PluginExporter:
    """Package a plugin directory for sharing or marketplace upload.

    Phase D stub: all methods raise NotImplementedError.
    """

    def export_to_zip(self, plugin_name: str, plugins_dir: str, output_path: str) -> str:
        """Export a plugin as a .zip archive."""
        raise NotImplementedError("Plugin export is not yet implemented")

    def export_to_tarball(self, plugin_name: str, plugins_dir: str, output_path: str) -> str:
        """Export a plugin as a .tar.gz archive."""
        raise NotImplementedError("Plugin export is not yet implemented")

    def validate_for_export(self, plugin_name: str, plugins_dir: str) -> list[str]:
        """Validate a plugin meets export requirements.

        Returns list of error strings (empty means ready for export).
        External plugins require: README.md, schemas/ directory.
        """
        raise NotImplementedError("Plugin export is not yet implemented")
