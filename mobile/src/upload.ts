// Pick a photo and upload it straight to Cloudinary using a signature from our API.
import * as ImagePicker from "expo-image-picker";
import { api, ApiError } from "./api";

type Sign = { upload_url: string; api_key: string; timestamp: number; folder: string; signature: string };
type Purpose = "rider_document" | "donation_photo" | "proof_photo";

/** Ask the user for a photo (camera or gallery). Returns the local file uri, or null if cancelled. */
export async function pickPhoto(source: "camera" | "gallery"): Promise<string | null> {
  const perm =
    source === "camera" ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!perm.granted) throw new Error(source === "camera" ? "Camera permission is needed" : "Photo access is needed");
  const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 0.7 };
  const result = source === "camera" ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
  if (result.canceled || !result.assets?.length) return null;
  return result.assets[0].uri;
}

/** Upload a local photo; returns its https URL on Cloudinary. */
export async function uploadPhoto(uri: string, purpose: Purpose): Promise<string> {
  const sign = await api<Sign>("/uploads/sign", { method: "POST", body: JSON.stringify({ purpose }) });
  const form = new FormData();
  const name = uri.split("/").pop() ?? "photo.jpg";
  // React Native's FormData accepts { uri, name, type } for files
  form.append("file", { uri, name, type: "image/jpeg" } as unknown as Blob);
  form.append("api_key", sign.api_key);
  form.append("timestamp", String(sign.timestamp));
  form.append("folder", sign.folder);
  form.append("signature", sign.signature);
  const res = await fetch(sign.upload_url, { method: "POST", body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.secure_url) {
    throw new ApiError(res.status, "upload_failed", data?.error?.message ?? "Upload failed. Try again.");
  }
  return data.secure_url as string;
}
