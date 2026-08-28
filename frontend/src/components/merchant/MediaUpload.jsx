import { useRef, useState } from "react";
import { Box, Button, Stack, Typography, CircularProgress } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

/**
 * A product image, uploaded for real.
 *
 * HOW THIS WORKS WITHOUT A FILE STORE:
 * There is no S3 bucket and no Firebase Storage here, so the picture is
 * resized in the browser and stored inline on the product document as a
 * data URI. That is a genuine constraint shaping the design rather than a
 * shortcut: a Firestore document caps at 1 MiB, and the catalogue endpoint
 * reads every product on every agent search, so a full-resolution photo
 * would either break the write or make discovery crawl.
 *
 * Hence the resize to MAX_EDGE and JPEG quality below — a card thumbnail
 * needs a few tens of kilobytes, not four megapixels. If the result is still
 * over the ceiling the upload is refused with the actual number, instead of
 * failing later inside Firestore where the reason would be invisible.
 *
 * The reference admin accepts video and 3D models. This accepts images,
 * because images are what the product card renders and an accepted file that
 * nothing can display is not a feature.
 */

const MAX_EDGE = 640;
const QUALITY = 0.72;
const MAX_STORED_BYTES = 180_000;

async function compress(file) {
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("That file could not be read."));
    reader.readAsDataURL(file);
  });

  const image = await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("That file is not an image this browser can open."));
    img.src = dataUrl;
  });

  const scale = Math.min(1, MAX_EDGE / Math.max(image.width, image.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(image.width * scale);
  canvas.height = Math.round(image.height * scale);
  canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);

  // PNG screenshots of flat colour compress worse as JPEG than they look, but
  // JPEG is the safe default for photographs and keeps transparency out of a
  // field that will be drawn on an opaque card anyway.
  return canvas.toDataURL("image/jpeg", QUALITY);
}

export default function MediaUpload({ value, onChange }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [dragging, setDragging] = useState(false);

  const accept = async (file) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Images only — the product card has nothing to do with a video.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const compressed = await compress(file);
      if (compressed.length > MAX_STORED_BYTES) {
        setError(
          `Still ${Math.round(compressed.length / 1024)}KB after resizing, over the `
          + `${Math.round(MAX_STORED_BYTES / 1024)}KB a product record can hold. Try a simpler image.`
        );
        return;
      }
      onChange(compressed);
    } catch (err) {
      setError(String(err.message ?? err));
    } finally {
      setBusy(false);
    }
  };

  if (value) {
    return (
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start" }}>
        <Box
          sx={{
            width: 96, height: 96, borderRadius: 2, overflow: "hidden",
            border: "1px solid", borderColor: "divider", flexShrink: 0,
          }}
        >
          <Box
            component="img"
            src={value}
            alt="Product"
            sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        </Box>
        <Stack spacing={0.75}>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            Stored on the product record, about {Math.round(value.length / 1024)}KB.
          </Typography>
          <Button
            size="small"
            startIcon={<CloseIcon sx={{ fontSize: 14 }} />}
            onClick={() => onChange("")}
            sx={{ alignSelf: "flex-start", color: "text.secondary" }}
          >
            Remove
          </Button>
        </Stack>
      </Stack>
    );
  }

  return (
    <Box>
      <Box
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          accept(e.dataTransfer.files?.[0]);
        }}
        sx={{
          border: "1px dashed",
          borderColor: dragging ? "text.secondary" : "divider",
          bgcolor: dragging ? "rgba(255,255,255,0.04)" : "transparent",
          borderRadius: 2,
          py: 3.5,
          px: 2,
          textAlign: "center",
          transition: "border-color 140ms, background-color 140ms",
        }}
      >
        {busy ? (
          <Stack spacing={1} sx={{ alignItems: "center" }}>
            <CircularProgress size={18} />
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              Resizing…
            </Typography>
          </Stack>
        ) : (
          <>
            <Button
              size="small"
              variant="outlined"
              onClick={() => inputRef.current?.click()}
              sx={{ mb: 1 }}
            >
              Upload new
            </Button>
            <Typography variant="caption" sx={{ color: "text.secondary", display: "block" }}>
              or drop an image here
            </Typography>
          </>
        )}

        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            accept(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </Box>

      <Typography variant="caption" sx={{ color: "text.secondary", mt: 0.75, display: "block", lineHeight: 1.6 }}>
        Images only, resized to {MAX_EDGE}px and kept on the product record — this store has no
        file storage, so a picture lives with the product or not at all.
      </Typography>

      {error && (
        <Typography variant="caption" sx={{ color: "error.main", mt: 0.75, display: "block" }}>
          {error}
        </Typography>
      )}
    </Box>
  );
}
