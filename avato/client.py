import os
import json
import queue
from concurrent import futures
from concurrent.futures import ProcessPoolExecutor
import logging
from itertools import repeat
from typing import List
from .config import AVATO_HOST, AVATO_PORT, AVATO_USE_SSL
from .api import API, Endpoints
from hashlib import sha256
from .storage import FileFormat, FileManifestBuilder, ChunkerBuilder, FileDescription, FileManifestMetadata, \
    FileManifest, StorageCipher

class ThreadPoolExecutorWithQueueSizeLimit(futures.ThreadPoolExecutor):
    def __init__(self, maxsize=50, *args, **kwargs):
        super(ThreadPoolExecutorWithQueueSizeLimit, self).__init__(*args, **kwargs)
        self._work_queue = queue.Queue(maxsize=maxsize)

class Client:
    class UnknownInstanceTypeError(Exception):
        """Raised when the instance type requested is not supported"""
        pass

    class UnknownUserEmail(Exception):
        """Raised when the user email doesn't exist"""
        pass

    class FileUploadError(Exception):
        """Raised when file upload fails"""
        pass

    def __init__(
        self,
        api_token,
        instance_types=[],
        backend_host=AVATO_HOST,
        backend_port=AVATO_PORT,
        use_ssl=AVATO_USE_SSL,
        http_proxy=None,
        https_proxy=None,
    ):
        self.registered_instances = instance_types
        self.api = API(
            api_token,
            backend_host,
            backend_port,
            use_ssl,
            http_proxy,
            https_proxy,
        )

    def get_instances(self):
        url = Endpoints.INSTANCES_COLLECTION
        response = self.api.get(url)
        return response.json()

    def _instance_from_type(self, type):
        for instance in self.registered_instances:
            if instance.type == type:
                return instance
        raise Client.UnknownInstanceTypeError

    def _get_user_id(self, email: str):
        url = f"{Endpoints.USERS_COLLECTION}?email={email}"
        response = self.api.get(url)
        users = response.json()
        if len(users) != 1:
            raise Client.UnknownUserEmail
        user_id = users[0]["id"]
        return user_id

    def get_instance(self, id):
        url = Endpoints.INSTANCE.replace(":instanceId", id)
        response = self.api.get(url)
        instance_info = response.json()
        instance_constructor = self._instance_from_type(instance_info["type"])
        return instance_constructor(
            self,
            id,
            instance_info["name"],
            instance_info["owner"],
        )

    def create_instance(self, name, type, participants):
        url = Endpoints.INSTANCES_COLLECTION
        data = {
            "name": name,
            "type": type,
            "participants": list(map(lambda x: {"id": self._get_user_id(x)}, participants)),
        }
        data_json = json.dumps(data)
        response = self.api.post(url, data_json, {"Content-type": "application/json"})
        response_json = response.json()
        instance_constructor = self._instance_from_type(type)
        return instance_constructor(self, response_json["id"], name, response_json["owner"])

    def upload_user_file(
        self,
        email: str,
        file_name: str,
        file_path: str,
        file_format: FileFormat,
        column_types: List[int],
        extra_entropy: bytes,
        key,
        chunk_size=8*1024**2,
        parallel_uploads=8
    ) -> FileDescription:
        user_id = self._get_user_id(email)
        uploader = ThreadPoolExecutorWithQueueSizeLimit(max_workers=parallel_uploads, maxsize=parallel_uploads*2)
        with ChunkerBuilder(file_path, column_types, file_format, extra_entropy, chunk_size=chunk_size) as chunker:
            # create manifest
            file_manifest_builder = FileManifestBuilder(file_name, file_format, extra_entropy, key is not None)
            file_manifest_builder.chunks = [a for a, _ in chunker]
            (manifest, manifest_metadata) = file_manifest_builder.build()
            logging.debug("manifest chunks:")
            logging.debug(file_manifest_builder.chunks)
            cipher = None
            if key is not None:
                cipher = StorageCipher(key)
                manifest.content = cipher.encrypt(manifest.content)
            file_description = self._upload_manifest(user_id, manifest, manifest_metadata)
            # upload chunks
            chunker.reset()
            for chunk in chunker:
                uploader.submit(self._upload_chunk, chunk[0], chunk[1], cipher, user_id, file_description.get("id"))
        uploader.shutdown(wait=True)
        return self.get_user_file(email, file_description.get("id"))

    def _upload_chunk(self, chunk_hash, chunk_data, cipher, user_id, file_id):
        url = Endpoints.USER_FILE_CHUNK \
            .replace(":userId", user_id) \
            .replace(":fileId", file_id) \
            .replace(":chunkHash", chunk_hash)
        if cipher is not None:
            chunk_data = cipher.encrypt(chunk_data)
        return self.api.post(url, chunk_data, {"Content-type": "application/octet-stream"})

    def _upload_manifest(self, user_id: str, manifest: FileManifest, manifest_metadata: FileManifestMetadata) -> FileDescription:
        manifest_metadata_json = json.dumps(dict(manifest_metadata))
        url = Endpoints.USER_FILES_COLLECTION.replace(":userId", user_id)
        parts = {
                "manifest": manifest.content,
                "metadata": manifest_metadata_json
                }
        response = self.api.post_multipart(url, parts)
        file_description: FileDescription = response.json()
        return file_description

    def delete_user_file(self, email: str, file_id: str):
        url = Endpoints.USER_FILE \
            .replace(":userId", self._get_user_id(email)) \
            .replace(":fileId", file_id)
        self.api.delete(url)

    def get_user_file(self, email: str, file_id: str) -> FileDescription:
        url = Endpoints.USER_FILE.replace(":userId", self._get_user_id(email)).replace(":fileId", file_id)
        response = self.api.get(url)
        return response.json()

    def get_user_files_collection(self, email: str) -> List[FileDescription]:
        url = Endpoints.USER_FILES_COLLECTION.replace(":userId", self._get_user_id(email))
        response = self.api.get(url)
        return response.json()
