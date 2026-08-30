import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, Typography, IconButton } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import ImageOutlinedIcon from "@mui/icons-material/ImageOutlined";
import SendIcon from "@mui/icons-material/ArrowUpward";
import LocalOfferIcon from "@mui/icons-material/LocalOfferOutlined";
import StarIcon from "@mui/icons-material/StarBorderOutlined";
import BoltIcon from "@mui/icons-material/BoltOutlined";
import SavingsIcon from "@mui/icons-material/SavingsOutlined";

/**
 * "+" menu — quick filters that append real phrases the intent parser
 * actually understands (it maps these to priority: discount / rating /
 * delivery_days / price). Mirrors the reference's "@" sources menu.
 */
/**
 * The one row in this menu that starts a search rather than narrowing one.
 * Kept beside the filters because the "+" is where people look for "what
 * else can I put in here", and a photo is the answer.
 */
const PHOTO_ROW = {
  key: "photo",
  label: "Search by photo",
  desc: "Match a picture against eBay's listings",
  icon: <ImageOutlinedIcon sx={{ fontSize: 16 }} />,
};

const QUICK_FILTERS = [
  { key: "discount", label: "Best discount", desc: "Prioritise deals", icon: <LocalOfferIcon sx={{ fontSize: 16 }} />, insert: "with the best discount" },
  { key: "rating", label: "Top rated", desc: "Prioritise reviews", icon: <StarIcon sx={{ fontSize: 16 }} />, insert: "with the highest rating" },
  { key: "fast", label: "Fast delivery", desc: "Prioritise speed", icon: <BoltIcon sx={{ fontSize: 16 }} />, insert: "with fast delivery" },
  { key: "budget", label: "Budget pick", desc: "Prioritise price", icon: <SavingsIcon sx={{ fontSize: 16 }} />, insert: "as cheap as possible" },
];

/** "/" menu — full runnable example queries, like the reference's slash commands. */
const TEMPLATES = [
  { key: "earbuds", label: "/earbuds", desc: "wireless earbuds under ₹2000, fast delivery", insert: "wireless earbuds under ₹2000, fast delivery" },
  { key: "deal", label: "/deal", desc: "earbuds under ₹3000 with the best discount", insert: "earbuds under ₹3000 with the best discount" },
  { key: "premium", label: "/premium", desc: "highest rated earbuds under ₹7000", insert: "highest rated earbuds under ₹7000" },
];

function parseSlash(draft) {
  const match = /(^|\s)\/([\w-]*)$/.exec(draft);
  return match ? { query: match[2].toLowerCase() } : null;
}

/**
 * Shrink a picture before it is sent.
 *
 * A phone photo is several megabytes of detail that a visual match does not
 * use, and base64 inflates it by a third on the way out. Resizing to fit
 * 1024px keeps the upload quick on a slow connection and keeps it inside
 * the size the server accepts, without changing what the photo is of.
 */
async function downscale(file, maxEdge = 1024, quality = 0.85) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  return canvas.toDataURL("image/jpeg", quality);
}

export default function PromptBar({ onSend, onImage, disabled, placeholder, tall = false }) {
  const [draft, setDraft] = useState("");
  const [plusOpen, setPlusOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [photo, setPhoto] = useState(null); // { dataUrl, name }
  const [photoError, setPhotoError] = useState(null);
  const [dragging, setDragging] = useState(false);
  const rootRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);

  const takeFile = async (file) => {
    setPhotoError(null);
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setPhotoError("That is not an image.");
      return;
    }
    try {
      setPhoto({ dataUrl: await downscale(file), name: file.name || "pasted image" });
      setPlusOpen(false);
    } catch {
      setPhotoError("That image could not be read.");
    }
  };

  const slash = parseSlash(draft);
  const menu = plusOpen ? "plus" : slash ? "slash" : null;
  const rows =
    menu === "plus"
      ? [PHOTO_ROW, ...QUICK_FILTERS]
      : menu === "slash"
        ? TEMPLATES.filter((t) => t.label.slice(1).startsWith(slash.query))
        : [];

  useEffect(() => setActiveIndex(0), [menu, slash?.query]);

  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [draft]);

  useEffect(() => {
    if (!plusOpen) return;
    const close = (e) => {
      if (!rootRef.current?.contains(e.target)) setPlusOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [plusOpen]);

  const pick = (row) => {
    if (row.key === "photo") {
      setPlusOpen(false);
      fileRef.current?.click();
      return;
    }
    if (menu === "plus") {
      setDraft((d) => (d.trim() ? `${d.trim()} ${row.insert}` : row.insert));
      setPlusOpen(false);
    } else {
      setDraft(row.insert);
    }
    inputRef.current?.focus();
  };

  // A photo is a request on its own; words beside it are optional and only
  // ever narrow it (a budget), never describe it.
  const canSend = (draft.trim().length > 0 || Boolean(photo)) && !disabled;
  const send = () => {
    if (!canSend) return;
    if (photo) {
      onImage?.({ imageB64: photo.dataUrl, note: draft.trim() });
      setPhoto(null);
    } else {
      onSend(draft.trim());
    }
    setDraft("");
    setPlusOpen(false);
  };

  return (
    <Box
      ref={rootRef}
      sx={{ position: "relative" }}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        takeFile(e.dataTransfer.files?.[0]);
      }}
    >
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          takeFile(e.target.files?.[0]);
          e.target.value = ""; // so the same file can be chosen twice
        }}
      />

      {(photo || photoError || dragging) && (
        <Box
          sx={{
            mb: 1, p: 1, borderRadius: 2, display: "flex", alignItems: "center", gap: 1,
            border: "1px dashed", borderColor: photoError ? "error.main" : "divider",
            bgcolor: "background.paper",
          }}
        >
          {photo && (
            <Box
              component="img"
              src={photo.dataUrl}
              alt=""
              sx={{ width: 40, height: 40, borderRadius: 1, objectFit: "cover", flexShrink: 0 }}
            />
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="caption" sx={{ display: "block", fontSize: 11.5 }}>
              {photoError
                ? photoError
                : photo
                  ? "Searching by this photo"
                  : "Drop a photo to search by it"}
            </Typography>
            {photo && (
              <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 10.5 }}>
                eBay matches the picture against its own listings — the agent does
                not identify the product. Add a budget in words if you want one.
              </Typography>
            )}
          </Box>
          {photo && (
            <IconButton
              size="small"
              onClick={() => { setPhoto(null); setPhotoError(null); }}
              sx={{ flexShrink: 0 }}
            >
              <CloseIcon sx={{ fontSize: 15 }} />
            </IconButton>
          )}
        </Box>
      )}

      {menu && rows.length > 0 && (
        <Box
          sx={{
            position: "absolute",
            bottom: "100%",
            left: 0,
            right: 0,
            mb: 1,
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2,
            p: 0.5,
            boxShadow: 6,
            animation: "commerce-studio-pop-in 180ms cubic-bezier(0.23,1,0.32,1) both",
          }}
        >
          {rows.map((row, i) => (
            <Box
              key={row.key}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => pick(row)}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1.25,
                px: 1.25,
                height: 36,
                borderRadius: 1.5,
                cursor: "pointer",
                bgcolor: i === activeIndex ? "action.hover" : "transparent",
              }}
            >
              {row.icon && <Box sx={{ color: "text.secondary", display: "flex" }}>{row.icon}</Box>}
              <Typography variant="body2" fontWeight={500} sx={{ flexShrink: 0 }}>
                {row.label}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap sx={{ flex: 1, minWidth: 0 }}>
                {row.desc}
              </Typography>
            </Box>
          ))}
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", px: 1.25, pt: 1, pb: 0.5, borderTop: "1px solid", borderColor: "divider", mt: 0.5 }}
          >
            {menu === "plus" ? "Add a filter to your request" : "Type to search templates"}
          </Typography>
        </Box>
      )}

      <Box
        sx={{
          display: "flex",
          flexDirection: tall ? "column" : "row",
          alignItems: tall ? "stretch" : "flex-end",
          gap: tall ? 1 : 0.5,
          bgcolor: "background.paper",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 2.5,
          p: tall ? 1.5 : 1,
          boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
          transition: "border-color 0.15s",
          "&:focus-within": { borderColor: "rgba(255,255,255,0.22)" },
        }}
      >
        <Box
          component="textarea"
          ref={inputRef}
          rows={1}
          value={draft}
          disabled={disabled}
          onChange={(e) => {
            setDraft(e.target.value);
            setPlusOpen(false);
          }}
          onKeyDown={(e) => {
            if (menu && rows.length > 0) {
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => (i + (e.key === "ArrowDown" ? 1 : rows.length - 1)) % rows.length);
                return;
              }
              if (e.key === "Enter" || e.key === "Tab") {
                e.preventDefault();
                pick(rows[activeIndex]);
                return;
              }
            }
            if (e.key === "Escape") {
              setPlusOpen(false);
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={placeholder ?? "Ask for anything — or paste a photo"}
          onPaste={(e) => {
            const file = [...(e.clipboardData?.items ?? [])]
              .find((i) => i.type.startsWith("image/"))?.getAsFile();
            if (file) {
              e.preventDefault();
              takeFile(file);
            }
          }}
          sx={{
            flex: 1,
            minWidth: 0,
            resize: "none",
            border: "none",
            outline: "none",
            bgcolor: "transparent",
            fontFamily: "inherit",
            fontSize: 14,
            lineHeight: 1.5,
            color: "text.primary",
            py: tall ? "4px" : "7px",
            minHeight: tall ? 48 : undefined,
            "&::placeholder": { color: "text.secondary" },
          }}
        />

        {/* Controls: their own row when tall, inline otherwise */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 1,
            flexShrink: 0,
            ...(tall ? {} : { order: 0 }),
          }}
        >
          <IconButton
            onClick={() => setPlusOpen((o) => !o)}
            sx={{
              width: 32,
              height: 32,
              borderRadius: 2,
              flexShrink: 0,
              bgcolor: plusOpen ? "action.selected" : "transparent",
            }}
          >
            <AddIcon sx={{ fontSize: 18 }} />
          </IconButton>

          <IconButton
            onClick={send}
            disabled={!canSend}
            sx={{
              width: 32,
              height: 32,
              borderRadius: 2,
              flexShrink: 0,
              bgcolor: canSend ? "primary.main" : "action.disabledBackground",
              color: canSend ? "#fff" : "text.disabled",
              transition: "background-color 0.15s, transform 0.1s",
              "&:hover": { bgcolor: canSend ? "primary.dark" : "action.disabledBackground" },
              "&:active": { transform: canSend ? "scale(0.94)" : "none" },
            }}
          >
            <SendIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Box>
      </Box>

      <style>{`
        @keyframes commerce-studio-pop-in {
          from { opacity: 0; transform: scale(0.97) translateY(4px); }
          to { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}</style>
    </Box>
  );
}