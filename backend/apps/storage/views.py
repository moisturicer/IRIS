from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from .models import StorageFolder, StorageFile
from .serializers import StorageFolderSerializer, StorageFileSerializer


class StorageListView(APIView):
    """
    GET /storage/?parent=<id>
    Returns folders and files inside the given parent (or root if no parent).
    Response shape: { folders: [...], files: [...], breadcrumb: [...] }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        parent_id = request.query_params.get("parent")
        parent    = None

        if parent_id:
            try:
                parent = StorageFolder.objects.get(pk=parent_id)
            except StorageFolder.DoesNotExist:
                return Response({"detail": "Folder not found."}, status=404)

        folders = StorageFolder.objects.filter(parent=parent).order_by("name")
        files   = StorageFile.objects.filter(folder=parent).order_by("name")

        # Build breadcrumb trail
        breadcrumb = []
        cursor = parent
        while cursor:
            breadcrumb.insert(0, {"id": cursor.id, "name": cursor.name})
            cursor = cursor.parent

        return Response({
            "folders":    StorageFolderSerializer(folders, many=True).data,
            "files":      StorageFileSerializer(files, many=True, context={"request": request}).data,
            "breadcrumb": breadcrumb,
        })


class StorageFolderListView(generics.ListCreateAPIView):
    """GET /storage/folders/ -- list + create folders."""
    serializer_class   = StorageFolderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        parent_id = self.request.query_params.get("parent")
        return StorageFolder.objects.filter(parent_id=parent_id).order_by("name")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class StorageFolderDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /storage/folders/<id>/"""
    serializer_class   = StorageFolderSerializer
    permission_classes = [IsAuthenticated]
    queryset           = StorageFolder.objects.all()


class StorageFileListView(generics.ListCreateAPIView):
    """GET /storage/files/ -- list files; POST to upload."""
    serializer_class   = StorageFileSerializer
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def get_queryset(self):
        folder_id = self.request.query_params.get("folder")
        return StorageFile.objects.filter(folder_id=folder_id).order_by("name")

    def perform_create(self, serializer):
        file_obj   = self.request.FILES.get("file")
        size_bytes = file_obj.size if file_obj else 0
        serializer.save(uploaded_by=self.request.user, size_bytes=size_bytes)


class StorageFileDetailView(generics.RetrieveDestroyAPIView):
    """GET/DELETE /storage/files/<id>/"""
    serializer_class   = StorageFileSerializer
    permission_classes = [IsAuthenticated]
    queryset           = StorageFile.objects.all()


class StorageFileDownloadView(APIView):
    """GET /storage/files/<id>/download/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from django.http import FileResponse
        try:
            f = StorageFile.objects.get(pk=pk)
        except StorageFile.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)
        return FileResponse(f.file.open("rb"), as_attachment=True, filename=f.name)
