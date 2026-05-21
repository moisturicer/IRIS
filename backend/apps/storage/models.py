from django.db import models


class StorageFolder(models.Model):
    """
    User-created folder for organizing files.
    Supports one level of nesting via the self-referential parent FK.
    TODO: enforce max depth in clean() if deep nesting is unwanted.
    """
    name       = models.CharField(max_length=200)
    parent     = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="created_folders"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self): return self.name


class StorageFile(models.Model):
    """A file attached to a StorageFolder (or loose at root if folder is null)."""
    name        = models.CharField(max_length=300)
    folder      = models.ForeignKey(
        StorageFolder, on_delete=models.CASCADE, null=True, blank=True, related_name="files"
    )
    file        = models.FileField(upload_to="storage/%Y/%m/")
    size_bytes  = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="stored_files"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self): return self.name

    @property
    def size_display(self):
        """Human-readable file size string."""
        n = self.size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"


# -------------------------------------------------------------------
# Legacy models kept for migration reference -- will be removed after
# data migration from the old file_management app.
# TODO: write a data migration that moves old Folder/Subfolder/File
#       rows to StorageFolder/StorageFile, then delete these classes.
# -------------------------------------------------------------------

class LegacyFolder(models.Model):
    """Old root folder model -- DO NOT use in new code."""
    name           = models.CharField(max_length=200)
    classification = models.ForeignKey(
        "records.Classification", on_delete=models.SET_NULL, null=True, related_name="legacy_folders"
    )

    class Meta:
        managed = False     # exclude from new migrations; exists for reference only
        db_table = "file_management_folder"
