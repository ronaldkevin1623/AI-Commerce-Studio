import { IconButton, Tooltip } from "@mui/material";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import StopCircleOutlinedIcon from "@mui/icons-material/StopCircleOutlined";
import VolumeUpOutlinedIcon from "@mui/icons-material/VolumeUpOutlined";
import VolumeOffOutlinedIcon from "@mui/icons-material/VolumeOffOutlined";

import { dictationSendsAudioAway } from "../../hooks/useVoice";

/**
 * The two voice controls, kept deliberately plain.
 *
 * Neither renders when the browser cannot do the thing behind it. A
 * microphone that does nothing when pressed teaches a shopper that the
 * app is broken, which is a worse outcome than the feature being absent.
 */

/** Push to talk. Says where the audio goes, because it goes somewhere. */
export function MicButton({ listening, onStart, onStop, disabled, size = 32 }) {
  const label = listening
    ? "Stop listening"
    : dictationSendsAudioAway
      ? "Speak your request. Your browser sends the audio to Google to turn it into text — nothing else here does that."
      : "Speak your request.";

  return (
    <Tooltip title={label} placement="top">
      <span>
        <IconButton
          onClick={listening ? onStop : onStart}
          disabled={disabled}
          aria-label={listening ? "Stop listening" : "Speak your request"}
          sx={{
            width: size,
            height: size,
            borderRadius: 2,
            color: listening ? "#F87171" : "text.secondary",
            bgcolor: listening ? "rgba(248,113,113,0.12)" : "transparent",
            "&:hover": { bgcolor: "rgba(255,255,255,0.06)" },
          }}
        >
          {listening
            ? <StopCircleOutlinedIcon sx={{ fontSize: size * 0.58 }} />
            : <MicNoneOutlinedIcon sx={{ fontSize: size * 0.58 }} />}
        </IconButton>
      </span>
    </Tooltip>
  );
}

/**
 * Read answers aloud, off by default.
 *
 * Default off is the whole design of this control: an agent that starts
 * talking on its own during a demo, or in an office, is a liability rather
 * than a feature. Speech synthesis runs on the device, so turning it on
 * sends nothing anywhere.
 */
export function SpeakToggle({ enabled, onToggle, speaking, size = 32 }) {
  return (
    <Tooltip
      title={enabled
        ? "Reading answers aloud. Spoken on this device — no audio leaves it."
        : "Read answers aloud"}
      placement="top"
    >
      <IconButton
        onClick={onToggle}
        aria-label={enabled ? "Stop reading answers aloud" : "Read answers aloud"}
        aria-pressed={enabled}
        sx={{
          width: size,
          height: size,
          borderRadius: 2,
          color: enabled ? "#4ADE80" : "text.secondary",
          bgcolor: enabled ? "rgba(74,222,128,0.12)" : "transparent",
          "&:hover": { bgcolor: "rgba(255,255,255,0.06)" },
          // A quiet pulse only while it is actually speaking, so the control
          // reports the live state rather than only the setting.
          animation: speaking ? "voicePulse 1.4s ease-in-out infinite" : "none",
          "@keyframes voicePulse": {
            "0%, 100%": { opacity: 1 },
            "50%": { opacity: 0.55 },
          },
        }}
      >
        {enabled
          ? <VolumeUpOutlinedIcon sx={{ fontSize: size * 0.58 }} />
          : <VolumeOffOutlinedIcon sx={{ fontSize: size * 0.58 }} />}
      </IconButton>
    </Tooltip>
  );
}
