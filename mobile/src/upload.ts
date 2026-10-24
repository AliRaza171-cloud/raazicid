// Pick a photo and upload it straight to Cloudinary using a signature from our API.
import * as ImagePicker from "expo-image-picker";
import { api, ApiError } from "./api";

type Sign = { upload_url: string; api_key: string; timestamp: number; folder: string; signature: string };
type Purpose = "rider_document" | "donation_photo" | "proof_photo";

/** A photo chosen on the phone: uri for showing it, base64 for uploading it. */
export type PickedPhoto = { uri: string; base64: string; mimeType: string };

/** Ask the user for a photo (camera or gallery). Returns null if cancelled. */
export async function pickPhoto(source: "camera" | "gallery"): Promise<PickedPhoto | null> {
  const perm =
    source === "camera" ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!perm.granted) throw new Error(source === "camera" ? "Camera permission is needed" : "Photo access is needed");
  const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 0.5, base64: true };
  const result = source === "camera" ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
  if (result.canceled || !result.assets?.length) return null;
  const a = result.assets[0];
  if (!a.base64) throw new Error("Could not read that photo. Try another one.");
  return { uri: a.uri, base64: a.base64, mimeType: a.mimeType ?? "image/jpeg" };
}

/**
 * Upload a photo; returns its https URL on Cloudinary.
 * Sent as JSON with a base64 data URI instead of multipart FormData: newer Expo versions
 * reject React Native's { uri, name, type } file parts ("Unsupported FormDataPart implementation").
 */
export async function uploadPhoto(photo: PickedPhoto, purpose: Purpose): Promise<string> {
  const sign = await api<Sign>("/uploads/sign", { method: "POST", body: JSON.stringify({ purpose }) });
  let res: Response;
  try {
    res = await fetch(sign.upload_url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        file: `data:${photo.mimeType};base64,${photo.base64}`,
        api_key: sign.api_key,
        timestamp: sign.timestamp,
        folder: sign.folder,
        signature: sign.signature,
      }),
    });
  } catch {
    throw new ApiError(0, "network", "Upload failed. Check your internet connection and try again.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data?.secure_url) {
    throw new ApiError(res.status, "upload_failed", data?.error?.message ?? "Upload failed. Try again.");
  }
  return data.secure_url as string;
}
