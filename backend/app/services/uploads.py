"""Signed direct uploads to Cloudinary.

The app asks the API for a signature, then sends the file straight to Cloudinary. The API secret
never leaves the server, and big files never pass through our backend.
"""

import hashlib
import time


def sign_params(params: dict[str, object], api_secret: str) -> str:
    """Cloudinary signature: sort params by name, join as a=1&b=2, append the secret, SHA-1."""
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    return hashlib.sha1((to_sign + api_secret).encode("utf-8")).hexdigest()


def upload_signature(cloud_name: str, api_key: str, api_secret: str, folder: str) -> dict:
    timestamp = int(time.time())
    return {
        "upload_url": f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
        "cloud_name": cloud_name,
        "api_key": api_key,
        "timestamp": timestamp,
        "folder": folder,
        "signature": sign_params({"folder": folder, "timestamp": timestamp}, api_secret),
    }
