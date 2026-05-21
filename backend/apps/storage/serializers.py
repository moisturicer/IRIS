from rest_framework import serializers
from .models import StorageFolder, StorageFile


class StorageFolderSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StorageFolder
        fields = ["id", "name", "parent", "created_by", "created_at", "updated_at"]
        read_only_fields = ["created_by", "created_at", "updated_at"]


class StorageFileSerializer(serializers.ModelSerializer):
    size_display = serializers.ReadOnlyField()
    file_url     = serializers.SerializerMethodField()

    class Meta:
        model  = StorageFile
        fields = [
            "id", "name", "folder", "file", "file_url",
            "size_bytes", "size_display", "uploaded_by", "uploaded_at",
        ]
        read_only_fields = ["uploaded_by", "uploaded_at", "size_bytes"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None
