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
import ShoppingBagIcon from "@mui/icons-material/ShoppingBagOutlined";
import FlightIcon from "@mui/icons-material/FlightTakeoffOutlined";
import { API_BASE } from "../../config";

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

/**
 * "/" is TWO menus, not one.
 *
 * Level 1 is the list of sectors, and it is fetched from `GET /sectors`
 * rather than written here. That is deliberate and it is the test of
 * whether the sector boundary is real: registering a third sector in the
 * backend has to make it appear in this menu with no edit to this file.
 * A hardcoded array would have looked identical on screen and quietly
 * meant the opposite.
 *
 * Level 2 is that sector's own templates, which arrive in the same
 * payload. `/deal` and `/premium` did not go anywhere — they are now
 * products' templates, one level down, exactly where they were before
 * plus a sector above them.
 */
const SECTOR_ICONS = {
  products: <ShoppingBagIcon sx={{ fontSize: 16 }} />,
  trip: <FlightIcon sx={{ fontSize: 16 }} />,
};

/**
 * Which level the "/" is on, given what has been typed.
 *
 * `/tr`        → level 1, filtering the sector list
 * `/trip `     → level 2, that sector's templates. The space matters: the
 *                sector is only committed once it is unambiguously ended,
 *                so typing `/trip` alone still lets you carry on typing.
 */
function parseSlash(draft, sectorIds) {
  const second = /(?:^|\s)\/([\w-]+)\s+(.*)$/.exec(draft);
  if (second && sectorIds.includes(second[1].toLowerCase())) {
    return { level: 2, sectorId: second[1].toLowerCase(), query: second[2].toLowerCase() };
  }
  const first = /(^|\s)\/([\w-]*)$/.exec(draft);
  return first ? { level: 1, sectorId: null, query: first[2].toLowerCase() } : null;
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

export default function PromptBar({ onSend, onImage, onSectorChange, activeSector,
                                    disabled, placeholder, tall = false }) {
  const [draft, setDraft] = useState("");
  const [plusOpen, setPlusOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [photo, setPhoto] = useState(null); // { dataUrl, name }
  const [photoError, setPhotoError] = useState(null);
  const [dragging, setDragging] = useState(false);
  // The sector list, from the registry. Empty until it arrives, which is
  // why the "/" menu degrades to nothing rather than to a stale hardcoded
  // list — a menu that lies about what is installed is worse than no menu.
  const [sectors, setSectors] = useState([]);
  const [sectorError, setSectorError] = useState(false);
  // A template's inserted text still matches the template it came
  // from, so without this the menu never closes and Enter re-picks
  // the same row forever instead of sending. Cleared on the next
  // keystroke, so typing another "/" reopens it.
  const [menuDismissed, setMenuDismissed] = useState(false);
  const rootRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/sectors`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => alive && setSectors(d.sectors || []))
      .catch(() => alive && setSectorError(true));
    return () => {
      alive = false;
    };
  }, []);

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

  const sectorIds = sectors.map((x) => x.sector_id);

  // Derived from a VALUE, not from state.
  //
  // The keydown handler used to read the `rows` of the last completed
  // render. Typing quickly meant Enter arrived before React had committed
  // the final keystroke, so the handler saw a menu that was no longer open
  // and swallowed the Enter — the first press did nothing and only the
  // second one sent. Passing the live textarea value in removes the
  // staleness rather than papering over it with a timeout.
  const menuFor = (value) =>
    plusOpen ? "plus"
      : (parseSlash(value, sectorIds) && !menuDismissed) ? "slash"
        : null;

  const rowsFor = (value) => {
    const kind = menuFor(value);
    const parsed = parseSlash(value, sectorIds);
    if (kind === "plus") return [PHOTO_ROW, ...QUICK_FILTERS];
    if (kind !== "slash" || !parsed) return [];
    if (parsed.level === 1 && sectorError) {
      return [{ key: "unavailable", label: "Sectors unavailable",
                desc: "The sector list could not be loaded — plain search still works",
                disabled: true }];
    }
    if (parsed.level === 1) {
      return sectors
        .filter((x) => x.sector_id.startsWith(parsed.query))
        .map((x) => ({
          key: x.sector_id, label: x.label, desc: x.description,
          icon: SECTOR_ICONS[x.sector_id] ?? null,
          isSector: true, sectorId: x.sector_id, insert: `${x.label} `,
        }));
    }
    const chosen = sectors.find((x) => x.sector_id === parsed.sectorId);
    return (chosen?.templates || [])
      .filter((t) => t.label.slice(1).startsWith(parsed.query)
                  || t.text.toLowerCase().includes(parsed.query))
      .map((t) => ({
        key: `${parsed.sectorId}:${t.key}`, label: t.label,
        desc: t.description, sectorId: parsed.sectorId, insert: t.text,
      }));
  };

  const slash = parseSlash(draft, sectorIds);
  const menu = menuFor(draft);

  const rows = rowsFor(draft);

  useEffect(() => setActiveIndex(0), [menu, slash?.level, slash?.query]);

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
    if (row.disabled) return;
    if (row.key === "photo") {
      setPlusOpen(false);
      fileRef.current?.click();
      return;
    }
    if (menu === "plus") {
      setDraft((d) => (d.trim() ? `${d.trim()} ${row.insert}` : row.insert));
      setPlusOpen(false);
    } else if (row.isSector) {
      // Choosing a sector SWITCHES THE AGENT, immediately — the heading,
      // the placeholder and the routing all change on this click. It does
      // not send anything.
      //
      // Whether the prefix stays in the box depends on whether this sector
      // has anything to show next. Products does — leaving "/products " up
      // opens its templates. Trip does not: it takes a sentence, so the box
      // is cleared and the person just types, exactly like a product
      // search. Leaving a dead "/trip " prefix there would be something to
      // delete before you could start.
      const chosen = sectors.find((x) => x.sector_id === row.sectorId);
      const hasTemplates = (chosen?.templates || []).length > 0;
      onSectorChange?.(row.sectorId);
      setDraft(hasTemplates ? row.insert : "");
      if (!hasTemplates) setMenuDismissed(true);
    } else {
      // A template from inside a sector keeps its prefix, so what is sent
      // still says which sector it belongs to.
      setDraft(row.sectorId ? `/${row.sectorId} ${row.insert}` : row.insert);
      setMenuDismissed(true);
    }
    inputRef.current?.focus();
  };

  // A photo is a request on its own; words beside it are optional and only
  // ever narrow it (a budget), never describe it.
  const canSend = (draft.trim().length > 0 || Boolean(photo)) && !disabled;

  // `value` is passed by the keydown handler so this reads the text as it
  // is at THIS keystroke. Typing fast (or pasting) and hitting Enter in the
  // same tick meant React had not re-rendered yet, so the closed-over
  // `draft` was still the previous value — empty on the first send, which
  // made canSend false and silently swallowed the Enter. The first press
  // did nothing and only the second one worked.
  const send = (value) => {
    const current = value === undefined ? draft : value;
    if (!((current.trim().length > 0 || Boolean(photo)) && !disabled)) return;
    if (photo) {
      onImage?.({ imageB64: photo.dataUrl, note: current.trim() });
      setPhoto(null);
    } else {
      // Strip the `/sector ` prefix off the text and pass the sector
      // alongside it. Products stays the default: with no prefix this is
      // exactly the call it always was, so the existing pipeline is
      // reached by the same path it always was.
      const text = current.trim();
      // `/trip` on its own SWITCHES MODE rather than sending an empty
      // request. Naming a sector is a statement about what you are doing
      // next, not a question — so the agent changes what it is for and
      // waits, instead of asking "a trip where?" before you have said
      // anything.
      const bare = /^\/([\w-]+)$/.exec(text);
      if (bare && sectorIds.includes(bare[1].toLowerCase())) {
        onSectorChange?.(bare[1].toLowerCase());
        setDraft("");
        setPhoto(null);
        setPlusOpen(false);
        return;
      }

      // `/trip <something>` switches AND runs, so the one-liner still works.
      const prefix = /^\/([\w-]+)\s+(.+)$/.exec(text);
      if (prefix && sectorIds.includes(prefix[1].toLowerCase())) {
        const id = prefix[1].toLowerCase();
        onSectorChange?.(id);
        onSend(prefix[2], { sectorId: id, source: "explicit_slash" });
      } else {
        // No prefix: whatever sector is currently active handles it.
        onSend(text);
      }
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
            {menu === "plus"
              ? "Add a filter to your request"
              : slash?.level === 2
                ? `${sectors.find((x) => x.sector_id === slash.sectorId)?.name ?? ""} templates — or just keep typing`
                : "Pick what kind of thing you are shopping for"}
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
            setMenuDismissed(false);
          }}
          onKeyDown={(e) => {
            // Live value, not the last render's. See rowsFor().
            const liveRows = rowsFor(e.target.value);
            const liveMenu = menuFor(e.target.value);
            if (liveMenu && liveRows.length > 0) {
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => (i + (e.key === "ArrowDown" ? 1 : liveRows.length - 1)) % liveRows.length);
                return;
              }
              if (e.key === "Enter" || e.key === "Tab") {
                e.preventDefault();
                pick(liveRows[Math.min(activeIndex, liveRows.length - 1)]);
                return;
              }
            }
            if (e.key === "Escape") {
              setPlusOpen(false);
              setMenuDismissed(true);
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(e.target.value);
              return;
            }
          }}
          placeholder={placeholder
            ?? (activeSector && activeSector !== "products"
              ? (sectors.find((x) => x.sector_id === activeSector)?.intent_schema
                  ?.find((f) => f.required)?.prompt
                 ?? "Tell me what you need")
              : "Ask for anything — or paste a photo")}
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