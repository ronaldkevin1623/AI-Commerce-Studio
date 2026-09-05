import { useCallback, useEffect, useRef, useState } from "react";

/**
 * VOICE, USING ONLY WHAT THE BROWSER ALREADY HAS.
 *
 * Two different APIs with two very different privacy stories, and this hook
 * keeps them apart rather than presenting "voice" as one feature:
 *
 *   speechSynthesis    — the agent speaking. Runs on the device. No network,
 *                        no account, no audio leaves the machine.
 *
 *   SpeechRecognition  — you speaking. Free and keyless, but Chrome and Edge
 *                        implement it by STREAMING THE AUDIO TO GOOGLE for
 *                        transcription. Firefox does not implement it at all.
 *
 * The second fact is the reason `dictationSendsAudioAway` is exported. A
 * microphone that quietly uploads a shop owner's voice would be the one
 * dishonest thing in a project whose whole claim is that it says what it
 * does with your data — so the UI states it, and the Your data page lists
 * it beside everything else that leaves.
 *
 * Nothing here is polyfilled or faked. Where the browser cannot do it,
 * `supported` is false and the control does not render: an inert microphone
 * button that silently does nothing is worse than no button.
 */

const Recognition =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

/** Chrome and Edge transcribe server-side. Stated, not buried. */
export const dictationSendsAudioAway = true;

export function useVoice({ onTranscript, lang = "en-IN" } = {}) {
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState(null);

  const recognitionRef = useRef(null);
  // The callback changes every render in most callers; holding it in a ref
  // means the recognition object does not have to be rebuilt to see the
  // current one, which would drop an in-flight result.
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const canDictate = Boolean(Recognition);
  const canSpeak =
    typeof window !== "undefined" && "speechSynthesis" in window;

  // ── The agent speaking ────────────────────────────────────────────────
  const speak = useCallback(
    (text) => {
      if (!canSpeak || !text) return;
      const utterance = new SpeechSynthesisUtterance(String(text));
      utterance.lang = lang;
      // Slightly under default: report figures read at full speed run
      // together, and a rupee amount misheard is worse than one read slowly.
      utterance.rate = 0.95;
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
      setSpeaking(true);
    },
    [canSpeak, lang]
  );

  const stopSpeaking = useCallback(() => {
    if (!canSpeak) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [canSpeak]);

  // ── You speaking ──────────────────────────────────────────────────────
  const startDictation = useCallback(() => {
    if (!canDictate || listening) return;
    setError(null);

    const recognition = new Recognition();
    recognition.lang = lang;
    // Push to talk, not always-on. A microphone that keeps its own counsel
    // about when it is listening is not a feature anybody asked for.
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    let latest = "";

    recognition.onresult = (event) => {
      let text = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        text += event.results[i][0].transcript;
      }
      latest = text;
      onTranscriptRef.current?.(text, event.results[0]?.isFinal ?? false);
    };

    recognition.onerror = (event) => {
      // "no-speech" and "aborted" are the user saying nothing and the user
      // stopping. Neither is a fault worth a red message.
      if (event.error !== "no-speech" && event.error !== "aborted") {
        setError(
          event.error === "not-allowed"
            ? "The microphone is blocked for this site."
            : `Dictation stopped: ${event.error}`
        );
      }
      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
      if (latest) onTranscriptRef.current?.(latest, true);
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
      setListening(true);
    } catch {
      // start() throws if called while already running; nothing to repair.
      setListening(false);
    }
  }, [canDictate, listening, lang]);

  const stopDictation = useCallback(() => {
    try {
      recognitionRef.current?.stop();
    } catch {
      /* already stopped */
    }
    setListening(false);
  }, []);

  // Leaving the page mid-sentence should not leave the browser talking, or
  // the microphone open.
  useEffect(
    () => () => {
      try {
        recognitionRef.current?.abort?.();
      } catch {
        /* nothing holding it */
      }
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    },
    []
  );

  return {
    canDictate,
    canSpeak,
    listening,
    speaking,
    error,
    startDictation,
    stopDictation,
    speak,
    stopSpeaking,
  };
}
