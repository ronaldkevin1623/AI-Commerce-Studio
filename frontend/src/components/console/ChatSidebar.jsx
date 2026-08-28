import { useEffect, useRef, useState } from "react";
import { Box, Stack, Typography, IconButton, InputBase, Tooltip } from "@mui/material";
import EditIcon from "@mui/icons-material/EditOutlined";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import MenuOpenIcon from "@mui/icons-material/MenuOpen";
import MenuIcon from "@mui/icons-material/Menu";

const EXPANDED_WIDTH = 288;
const COLLAPSED_WIDTH = 56;
const ROW_HEIGHT = 36;
const SIDE_PAD = 1.25;

/**
 * Session history sidebar. No app mark here — the header already
 * carries the logo, so repeating it just costs vertical space.
 * Every row shares the same height, radius and left inset so icons
 * and labels line up down a single axis.
 */
export default function ChatSidebar({ turns, activeId, onSelect, onNewChat, collapsed, onToggleCollapse }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const searchRef = useRef(null);

  useEffect(() => {
    if (searchOpen) searchRef.current?.focus();
  }, [searchOpen]);

  const closeSearch = () => {
    setSearchOpen(false);
    setQuery("");
  };

  const visibleTurns = turns.filter((t) =>
    t.query.toLowerCase().includes(query.trim().toLowerCase())
  );

  // Shared row geometry keeps icons on one vertical axis whether the
  // row is a button, a section header, or a history entry.
  const rowSx = {
    display: "flex",
    alignItems: "center",
    gap: 1.5,
    height: ROW_HEIGHT,
    px: 1.25,
    borderRadius: 2,
    cursor: "pointer",
    "&:hover": { bgcolor: "action.hover" },
  };

  const iconSx = { fontSize: 18, flexShrink: 0, color: "text.secondary" };

  return (
    <Box
      sx={{
        width: collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH,
        flexShrink: 0,
        borderRight: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.28s cubic-bezier(0.16, 1, 0.3, 1)",
        overflow: "hidden",
      }}
    >
      {/* Collapse control sits alone at the top — same row height and
          inset as everything below it. */}
      <Box sx={{ px: SIDE_PAD, pt: 1.5, pb: 0.5 }}>
        <Tooltip title={collapsed ? "Expand" : "Collapse"} placement="right">
          <IconButton
            onClick={onToggleCollapse}
            sx={{
              width: ROW_HEIGHT,
              height: ROW_HEIGHT,
              borderRadius: 2,
              color: "text.secondary",
            }}
          >
            {collapsed ? <MenuIcon sx={{ fontSize: 18 }} /> : <MenuOpenIcon sx={{ fontSize: 18 }} />}
          </IconButton>
        </Tooltip>
      </Box>

      {/* New chat */}
      <Box sx={{ px: SIDE_PAD }}>
        <Tooltip title={collapsed ? "New chat" : ""} placement="right">
          <Box onClick={onNewChat} sx={rowSx}>
            <EditIcon sx={{ ...iconSx, color: "text.primary" }} />
            {!collapsed && (
              <Typography variant="body2" fontWeight={500} noWrap>
                New chat
              </Typography>
            )}
          </Box>
        </Tooltip>
      </Box>

      {/* Chats header / inline search */}
      {!collapsed && (
        <Box sx={{ px: SIDE_PAD, mt: 2, mb: 0.5 }}>
          {!searchOpen ? (
            <Box sx={{ ...rowSx, cursor: "default", "&:hover": { bgcolor: "transparent" } }}>
              <Typography
                variant="caption"
                fontWeight={600}
                color="text.secondary"
                sx={{ flex: 1, textTransform: "uppercase", letterSpacing: "0.06em", fontSize: 11 }}
              >
                Chats
              </Typography>
              <IconButton
                size="small"
                onClick={() => setSearchOpen(true)}
                sx={{ color: "text.secondary" }}
              >
                <SearchIcon sx={{ fontSize: 16 }} />
              </IconButton>
            </Box>
          ) : (
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                height: ROW_HEIGHT,
                px: 1.25,
                borderRadius: 2,
                bgcolor: "background.default",
              }}
            >
              <SearchIcon sx={{ fontSize: 16, color: "text.secondary", mr: 1 }} />
              <InputBase
                inputRef={searchRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && closeSearch()}
                placeholder="Search chats"
                sx={{ flex: 1, fontSize: 13 }}
              />
              <IconButton size="small" onClick={closeSearch} sx={{ color: "text.secondary" }}>
                <CloseIcon sx={{ fontSize: 15 }} />
              </IconButton>
            </Box>
          )}
        </Box>
      )}

      {/* History */}
      <Box sx={{ flex: 1, overflowY: "auto", px: SIDE_PAD }}>
        {!collapsed && visibleTurns.length === 0 && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", px: 1.25, py: 1.5, lineHeight: 1.6 }}
          >
            {query ? "No chats found" : "Your requests will appear here"}
          </Typography>
        )}

        <Stack spacing={0.25}>
          {visibleTurns.map((turn) => {
            const active = turn.id === activeId;
            return (
              <Tooltip key={turn.id} title={collapsed ? turn.query : ""} placement="right">
                <Box
                  onClick={() => onSelect(turn.id)}
                  sx={{
                    ...rowSx,
                    bgcolor: active ? "action.selected" : "transparent",
                  }}
                >
                  <ChatBubbleOutlineIcon
                    sx={{ ...iconSx, color: active ? "text.primary" : "text.secondary" }}
                  />
                  {!collapsed && (
                    <Typography
                      variant="body2"
                      noWrap
                      sx={{
                        color: active ? "text.primary" : "text.secondary",
                        fontWeight: active ? 600 : 400,
                      }}
                    >
                      {turn.query}
                    </Typography>
                  )}
                </Box>
              </Tooltip>
            );
          })}
        </Stack>
      </Box>

      {/* Status footer */}
      {!collapsed && (
        <Box sx={{ px: SIDE_PAD, py: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              height: 32,
              px: 1.25,
              borderRadius: 2,
              bgcolor: "background.default",
            }}
          >
            <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: "success.main", flexShrink: 0 }} />
            <Typography variant="caption" color="text.secondary" noWrap>
              Razorpay test mode
            </Typography>
          </Box>
        </Box>
      )}
    </Box>
  );
}